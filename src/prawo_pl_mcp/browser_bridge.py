"""Klient tylko do wewnętrznej usługi browser fallback.

URL konfigurowany przez operatora, nie przez argument MCP.
Nie omija CAPTCHA, WAF ani logowania. Nie wystawia nowych tooli modelowi.
"""
from __future__ import annotations

import os


async def browser_fallback(tool: str, args: dict) -> dict:
    if tool not in ("fetch_celex_pl", "fetch_orzeczenie_po_sygnaturze", "fetch_eli_pdf"):
        raise ValueError("Niedozwolone narzędzie przeglądarki")
    url = os.environ.get("PRAWO_WEBWRIGHT_MCP_URL", "").strip()
    if not url:
        return {"status": "niepodłączony_webwright",
                "uwaga": "Nie skonfigurowano wewnętrznego serwera Playwright"}
    # Klient powstaje dopiero gdy lokalne źródła nie dały wyniku.
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport
    try:
        async with Client(StreamableHttpTransport(url), timeout=160) as client:
            response = await client.call_tool(tool, args)
            if getattr(response, "is_error", False):
                return {"status": "błąd_źródła",
                        "uwaga": "Przeglądarka zwróciła błąd; wynik nie został oznaczony jako pełny"}
            value = getattr(response, "structured_content", None)
            if isinstance(value, dict):
                if set(value) == {"result"} and isinstance(value["result"], dict):
                    return value["result"]
                return value
            value = getattr(response, "data", None)
            if isinstance(value, dict):
                return value
            return {"status": "niezweryfikowany_wynik",
                    "uwaga": "Brak odpowiedzi ustrukturyzowanej; nie zapisano pełnego tekstu"}
    except Exception as exc:
        return {"status": "błąd_źródła", "uwaga": f"Problem usługi Webwright: {type(exc).__name__}"}
