"""Bounded HTTPS client for the stand-alone AED importer."""
import ipaddress
import json
import socket
import time
from urllib.parse import urlencode, urlsplit, urljoin
import requests


class ImportBlocked(RuntimeError):
    pass


class Client:
    def __init__(self, max_file, max_total):
        self.max_file = max_file
        self.max_total = max_total
        self.downloaded_bytes = 0
        self.downloads = 0
        self.trusted_origin = None
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "MCOD-AED-Pilot/1.0", "Accept-Encoding": "identity"})

    def request(self, method, url):
        for redirect in range(6):
            parsed = urlsplit(url)
            if (parsed.scheme != "https" or parsed.username or parsed.password or
                    (parsed.port not in (None, 443) and parsed.netloc != self.trusted_origin)):
                raise ImportBlocked("Only credential-free standard HTTPS URLs are allowed.")
            addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
            # Replit resolves its own preview host to an internal proxy IP.
            # Only the configured application origin is permitted that exception;
            # public source file URLs never receive it.
            if (not addresses or (parsed.netloc != self.trusted_origin and
                                  any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses))):
                raise ImportBlocked("Non-public network destination refused.")
            for attempt in range(4):
                time.sleep(0.3 + attempt)
                try:
                    response = self.session.request(method, url, timeout=(10, 35), stream=True,
                                                    allow_redirects=False)
                except requests.RequestException:
                    if attempt == 3:
                        raise
                    time.sleep(2 ** attempt)
                    continue
                if response.status_code not in (429, 500, 502, 503, 504):
                    break
                retry = response.headers.get("Retry-After", "")
                response.close()
                time.sleep(min(60, int(retry) if retry.isdigit() else 2 ** attempt))
            if response.is_redirect:
                target = urljoin(url, response.headers["Location"])
                response.close()
                url = target
                continue
            try:
                response.raise_for_status()
            except requests.HTTPError:
                response.close()
                raise
            return response
        raise ImportBlocked("Too many redirects.")

    def json(self, url):
        with self.request("GET", url) as response:
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > 8 * 1024 * 1024:
                    raise ImportBlocked("Metadata response exceeds 8 MiB.")
            return json.loads(data)

    def pages(self, base, params):
        cursor, seen = 0, set()
        while True:
            query = dict(params, per_page=100, sort="id")
            if cursor:
                query["id[gt]"] = cursor
            page = self.json(base + "?" + urlencode(query))
            rows = page.get("data", [])
            if not rows:
                return
            for row in rows:
                ident = int(row["id"])
                if ident <= cursor or ident in seen:
                    raise ImportBlocked("Source pagination repeated or ignored its cursor.")
                seen.add(ident)
                yield row
            cursor = max(int(row["id"]) for row in rows)
            if len(rows) < 100:
                return

    def download(self, url, expected):
        if (not isinstance(expected, int) or isinstance(expected, bool) or
                expected <= 0 or expected > self.max_file):
            raise ImportBlocked("File size is unknown or exceeds limit.")
        if expected + self.downloaded_bytes > self.max_total:
            raise ImportBlocked("Total transfer limit exceeded.")
        # API metadata supplies a known size even when a host refuses HEAD.
        with self.request("HEAD", url) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) != expected:
                raise ImportBlocked("HEAD length differs from source metadata; refresh required.")
        with self.request("GET", url) as response:
            data = bytearray()
            for chunk in response.iter_content(65536):
                self.downloaded_bytes += len(chunk)
                data.extend(chunk)
                if len(data) > expected or self.downloaded_bytes > self.max_total:
                    raise ImportBlocked("File exceeded declared size or transfer budget.")
            if len(data) != expected:
                raise ImportBlocked("Downloaded length differs from declared length.")
        self.downloads += 1
        return bytes(data)
