"""Streamable HTTP endpoint for the independent MS MCP."""
from server import mcp
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


async def healthz(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "ms"})


app = mcp.http_app()
app.routes.append(Route("/healthz", endpoint=healthz, methods=["GET"]))
