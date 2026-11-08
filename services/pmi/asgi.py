from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from server import mcp


async def healthz(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "pmi"})


app = mcp.http_app()
app.routes.append(Route("/healthz", endpoint=healthz, methods=["GET"]))
