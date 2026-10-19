import os
import socket
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from http.client import HTTPConnection
from unittest.mock import patch

from hg.phone_runtime import PhoneRuntime
from hg.server import HGHTTPServer, main


READ_TOKEN = "test-limit-read-token"
WRITE_TOKEN = "test-limit-write-token"


class ServerLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {
            "HG_API_READ_TOKEN": READ_TOKEN,
            "HG_API_WRITE_TOKEN": WRITE_TOKEN,
            "HG_API_READ_TOKEN_ID": "read-v1",
            "HG_API_WRITE_TOKEN_ID": "write-v1",
            "HG_API_READ_TOKEN_EXPIRES_AT": "4102444800",
            "HG_API_WRITE_TOKEN_EXPIRES_AT": "4102444800",
            "HG_API_REVOKED_TOKEN_IDS": "",
            "HG_API_PRINCIPAL_ID": "test-owner",
            "HG_MEMORY_READ_SCOPES": "owner,global,HG",
            "HG_MEMORY_WRITE_SCOPES": "owner,global,HG",
            "HG_MAX_CONNECTIONS": "4",
            "HG_REQUEST_TIMEOUT_SECONDS": "1.0",
            "HG_RATE_LIMIT_REQUESTS": "120",
            "HG_RATE_LIMIT_WINDOW_SECONDS": "60",
        }, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.runtime = PhoneRuntime(state_dir=self.tmp.name)

    def start_server(self):
        self.server = HGHTTPServer(("127.0.0.1", 0), runtime=self.runtime)
        self.thread = __import__("threading").Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def stop_server(self):
        if getattr(self, "server", None):
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
            self.server = None

    def test_http_429_has_retry_after(self):
        with patch.dict(os.environ, {"HG_RATE_LIMIT_REQUESTS": "2", "HG_RATE_LIMIT_WINDOW_SECONDS": "60"}):
            self.start_server()
        for _ in range(2):
            with urllib.request.urlopen(self.base + "/", timeout=2) as response:
                self.assertEqual(response.status, 200)
                response.read()
        request = urllib.request.Request(self.base + "/")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=2)
        with ctx.exception as response:
            self.assertEqual(response.code, 429)
            self.assertEqual(response.headers.get("Retry-After") is not None, True)
            self.assertEqual(response.read().decode(), '{"error":{"code":"RATE_LIMITED"},"ok":false}')

    def test_slow_request_line_is_closed_by_socket_deadline(self):
        with patch.dict(os.environ, {"HG_REQUEST_TIMEOUT_SECONDS": "0.15"}):
            self.start_server()
        client = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=2)
        self.addCleanup(client.close)
        client.sendall(b"GET /api/health HTTP/1.1")
        time.sleep(0.35)
        client.settimeout(1)
        try:
            response = client.recv(1)
        except (ConnectionResetError, socket.timeout):
            response = b""
        self.assertEqual(response, b"")

    def test_slow_headers_are_not_dispatched(self):
        with patch.dict(os.environ, {"HG_REQUEST_TIMEOUT_SECONDS": "0.15"}):
            self.start_server()
        calls = []
        original_health = self.runtime.health
        self.runtime.health = lambda: (calls.append("health") or original_health())
        client = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=2)
        self.addCleanup(client.close)
        client.sendall(b"GET /api/health HTTP/1.1\r\nHost: localhost\r\nX-Partial:")
        time.sleep(0.35)
        client.settimeout(1)
        try:
            response = client.recv(1)
        except (ConnectionResetError, socket.timeout):
            response = b""
        self.assertEqual(response, b"")
        self.assertEqual(calls, [], "incomplete headers must never dispatch the route")

    def test_slow_request_body_times_out_without_mutation(self):
        with patch.dict(os.environ, {"HG_REQUEST_TIMEOUT_SECONDS": "0.15"}):
            self.start_server()
        before = self.runtime.store.verify()
        client = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=2)
        self.addCleanup(client.close)
        request = (
            "POST /api/memory HTTP/1.1\r\n"
            "Host: localhost\r\n"
            f"Authorization: Bearer {WRITE_TOKEN}\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: 100\r\n\r\n"
        ).encode("ascii")
        client.sendall(request + b"{")
        time.sleep(0.35)
        client.settimeout(1)
        response = client.recv(4096)
        self.assertIn(b"HTTP/1.1 408 Request Timeout", response)
        self.assertIn(b"REQUEST_TIMEOUT", response)
        self.assertEqual(self.runtime.store.verify(), before)

    def test_connection_budget_returns_503_and_retry_after(self):
        with patch.dict(os.environ, {"HG_MAX_CONNECTIONS": "1", "HG_REQUEST_TIMEOUT_SECONDS": "0.5"}):
            self.start_server()
        slow = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=2)
        self.addCleanup(slow.close)
        time.sleep(0.08)
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        self.addCleanup(conn.close)
        conn.request("GET", "/api/health")
        response = conn.getresponse()
        self.assertEqual(response.status, 503)
        self.assertEqual(response.getheader("Retry-After"), "1")
        response.read()

    def test_invalid_connection_configuration_fails_closed(self):
        with patch.dict(os.environ, {"HG_MAX_CONNECTIONS": "0"}):
            with self.assertRaisesRegex(RuntimeError, "HG_MAX_CONNECTIONS"):
                HGHTTPServer(("127.0.0.1", 0), runtime=self.runtime)

    def test_main_refuses_public_cleartext_bind(self):
        with patch("hg.server.validate_build", return_value={"ok": True}), \
             patch.dict(os.environ, {"HG_BIND": "0.0.0.0"}):
            with self.assertRaisesRegex(RuntimeError, "loopback"):
                main()


if __name__ == "__main__":
    unittest.main()
