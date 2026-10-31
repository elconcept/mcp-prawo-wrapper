"""Wewnętrzny ASGI dla browser-fallback; nie publikować w portalu lex.

Dostęp do tej usługi tylko z prywatnej sieci Dockera. API key jest zalecany
dla środowisk współdzielonych; domyślna usługa nie ma hostowego mapowania portu.
"""
from __future__ import annotations

from .webwright_internal import mcp

app = mcp.http_app()
