"""Jeden endpoint Streamable HTTP dla resolvera (nie jest to Repertorium)."""
from __future__ import annotations

import hmac
import os

from .slim_resolver import mcp

_inner = mcp.http_app()


async def app(scope, receive, send):
    if scope["type"] != "http":
        await _inner(scope, receive, send)
        return
    expected = os.environ.get("PRAWO_PL_MCP_API_KEY")
    if expected:
        headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                   for k, v in scope.get("headers", [])}
        supplied = headers.get("x-api-key")
        if not supplied:
            authorization = headers.get("authorization", "")
            if authorization.lower().startswith("bearer "):
                supplied = authorization.split(" ", 1)[1].strip()
        if not supplied or not hmac.compare_digest(supplied, expected):
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"text/plain; charset=utf-8")]})
            await send({"type": "http.response.body", "body": b"Unauthorized"})
            return
    await _inner(scope, receive, send)
