"""Focused publishing checks. No real database, users, or service data."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PythonRuntimeTests(unittest.TestCase):
    def test_wrapper_enforces_native_extension_compatibility(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            interpreter = runtime / "python/cpython-3.8.20-linux-x86_64-gnu/bin/python3.8"
            interpreter.parent.mkdir(parents=True)
            (runtime / "site-packages/django").mkdir(parents=True)
            interpreter.write_text(
                '#!/usr/bin/env bash\n'
                'printf "%s %s %s" "$PURE_PYTHON" "$PYTHONFAULTHANDLER" "$CELERY_SKIP_CHECKS"\n'
            )
            interpreter.chmod(0o755)
            result = subprocess.run(
                ["env", "PURE_PYTHON=0", "PYTHONFAULTHANDLER=0", "CELERY_SKIP_CHECKS=",
                 "MCOD_RUNTIME_ROOT=" + directory,
                 "bash", str(ROOT / "scripts/replit/python.sh")],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b"1 1 1")


class Upstream(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/":
            # Django's anonymous admin index redirects without authenticating.
            self.send_response(302)
            self.send_header("Location", "/login/?next=/")
            body = b""
        else:
            self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" and self.headers.get("Cookie") != "test-authenticated":
            self.send_response(302)
            self.send_header("Location", "/login/?next=/")
            body = b""
        elif self.path.startswith("/resources/"):
            self.send_response(302)
            self.send_header("Location", "/login/")
            body = b""
        else:
            self.send_response(200)
            body = b"login-form" if self.path.startswith("/login/") else b"dashboard"
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class PublishingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.backend = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        threading.Thread(target=cls.backend.serve_forever, daemon=True).start()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        config = (ROOT / "scripts/replit/nginx.conf").read_text()
        config = config.replace("listen 0.0.0.0:5000", "listen 127.0.0.1:" + str(cls.port))
        config = config.replace("127.0.0.1:8001", "127.0.0.1:" + str(cls.backend.server_port))
        config = config.replace("/tmp/mcod-nginx.pid", cls.temp.name + "/nginx.pid")
        config = config.replace("@STATIC_ROOT@", str(ROOT / "statics"))
        path = Path(cls.temp.name) / "nginx.conf"
        path.write_text(config)
        cls.nginx = subprocess.Popen(
            ["nginx", "-p", cls.temp.name, "-c", str(path), "-g", "daemon off;"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(100):
            if cls.nginx.poll() is not None:
                raise RuntimeError(cls.nginx.stderr.read().decode())
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("Test proxy did not start.")

    @classmethod
    def tearDownClass(cls):
        cls.nginx.terminate()
        cls.nginx.wait(timeout=10)
        cls.nginx.stderr.close()
        cls.backend.shutdown()
        cls.backend.server_close()
        cls.temp.cleanup()

    def request(self, path, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("GET", path, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_anonymous_root_displays_real_login_for_publish_probe(self):
        self.assertEqual(self.request("/"), (200, b"login-form"))

    def test_authenticated_dashboard_is_not_rewritten(self):
        self.assertEqual(self.request("/", {"Cookie": "test-authenticated"}), (200, b"dashboard"))

    def test_other_protected_pages_still_redirect_to_login(self):
        self.assertEqual(self.request("/resources/resource/")[0], 302)

    def test_login_form_posts_to_named_login_route_not_current_page(self):
        template = (ROOT / "mcod/templates/admin/login.html").read_text()
        self.assertIn('action="{% url \'login\' %}"', template)
        self.assertNotIn('action="{{ app_path }}"', template)

    def test_old_root_form_preserves_post_instead_of_silent_get(self):
        body = b"username=fixture&password=not-a-real-password&next=%2F"
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("POST", "/", body=body, headers={
                "Content-Type": "application/x-www-form-urlencoded",
            })
            response = connection.getresponse()
            self.assertEqual(response.status, 307)
            target = response.getheader("Location")
            self.assertEqual(target, "/login/")
            response.read()
            # A browser follows 307 using the SAME POST and body.
            connection.request("POST", "/login/", body=body, headers={
                "Content-Type": "application/x-www-form-urlencoded",
            })
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), body)
        finally:
            connection.close()

    def test_launchers_do_not_run_health_probes(self):
        for name in ("start.sh", "run-production.sh", "build.sh"):
            source = (ROOT / "scripts/replit" / name).read_text()
            for probe in ("aed_storage_check", "redis-cli", "/dev/tcp", "curl "):
                self.assertNotIn(probe, source)


if __name__ == "__main__":
    unittest.main()
