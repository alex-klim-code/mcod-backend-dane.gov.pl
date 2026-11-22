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
                'printf "%s %s" "$PURE_PYTHON" "$PYTHONFAULTHANDLER"\n'
            )
            interpreter.chmod(0o755)
            result = subprocess.run(
                ["env", "PURE_PYTHON=0", "PYTHONFAULTHANDLER=0",
                 "MCOD_RUNTIME_ROOT=" + directory,
                 "bash", str(ROOT / "scripts/replit/python.sh")],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b"1 1")


class Upstream(BaseHTTPRequestHandler):
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

    def test_missing_production_services_fail_before_starting_children(self):
        result = subprocess.run(
            ["bash", "-c", 'MCOD_RUNTIME_ROOT="$1" bash "$2"', "test",
             self.temp.name + "/missing-runtime", str(ROOT / "scripts/replit/services.sh")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"Elasticsearch runtime is missing", result.stderr)


if __name__ == "__main__":
    unittest.main()
