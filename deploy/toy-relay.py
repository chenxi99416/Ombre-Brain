#!/usr/bin/env python3
"""
Toy Relay: lightweight HTTP command relay running on VPS.
CC posts commands here, Mac's toy-bridge.py polls them.

Usage on VPS:
  python3 toy-relay.py &

CC sends commands via:
  curl -X POST http://localhost:8080 -d '{"action":"vibrate","intensity":0.5}'
  curl -X POST http://localhost:8080 -d '{"action":"pulse","count":3}'
  curl -X POST http://localhost:8080 -d '{"action":"wave"}'
  curl -X POST http://localhost:8080 -d '{"action":"off"}'
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading

command_queue = []
lock = threading.Lock()


class RelayHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        with lock:
            cmds = list(command_queue)
            command_queue.clear()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(cmds).encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        with lock:
            command_queue.append(body)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
        print(f"Queued: {body}")

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    port = 8080
    print(f"Toy Relay listening on :{port}")
    print("CC can send: curl -X POST http://localhost:8080 -d '{\"action\":\"vibrate\",\"intensity\":0.5}'")
    HTTPServer(("0.0.0.0", port), RelayHandler).serve_forever()
