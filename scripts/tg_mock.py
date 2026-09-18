import json
from http.server import BaseHTTPRequestHandler, HTTPServer

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        with open("/tmp/tg_calls.log", "a") as f:
            f.write(self.path + "\n" + body.decode() + "\n===\n")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "result": {"message_id": 42, "chat": {"id": 111}}}).encode())
    def log_message(self, *a):
        pass

HTTPServer(("127.0.0.1", 9999), H).serve_forever()
