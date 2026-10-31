"""Loopback test servers and test fixtures for macos_parity tests.

Provides:
- Loopback HTTP/1.1 and HTTP/2 servers
- Echo and headers inspection endpoints
- Compression endpoints (gzip, brotli, zstd)
"""

import http.server
import socketserver
import threading
from urllib.parse import urlparse

class MockHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        elif parsed.path == "/echo":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok", "url": "/echo"}')
        elif parsed.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/echo")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Quiet down server logs during tests


class LoopbackServer:
    def __init__(self, port=0):
        self.server = socketserver.TCPServer(("127.0.0.1", port), MockHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
