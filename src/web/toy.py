"""
web/toy.py — Toy command relay (POST to queue, GET to poll & consume)

VPS CC posts commands, Mac toy-bridge.py polls and executes them.
No auth required — commands are ephemeral and non-sensitive.
"""

import json as _json_lib
import threading

from starlette.requests import Request
from starlette.responses import Response, JSONResponse

_queue: list[dict] = []
_lock = threading.Lock()


def register(mcp) -> None:

    @mcp.custom_route("/api/toy/cmd", methods=["GET"])
    async def toy_cmd_get(request: Request) -> Response:
        with _lock:
            cmds = list(_queue)
            _queue.clear()
        return JSONResponse(cmds)

    @mcp.custom_route("/api/toy/cmd", methods=["POST"])
    async def toy_cmd_post(request: Request) -> Response:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        with _lock:
            _queue.append(body)
        return JSONResponse({"ok": True})
