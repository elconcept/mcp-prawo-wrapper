"""Regresja: MCP structuredContent nie może ginąć w puli klientów.

Nie pobiera danych ani nie uruchamia prawdziwych kontenerów.
"""
from types import SimpleNamespace

from prawo_pl_mcp.pool import SourcePool
from prawo_pl_mcp.registry import SOURCES


class FakeClient:
    async def call_tool(self, name, args):
        assert name == "get_judgment"
        assert args == {"id": 166511, "offset": 5000, "limit": 5000}
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="Kolejna część uzasadnienia")],
            structured_content={
                "totalLength": 12000,
                "returnedLength": 5000,
                "offset": 5000,
                "hasMore": True,
                "nextOffset": 10000,
                "citations": [{"title": "V CSK 145/14", "url": "https://www.saos.org.pl/judgments/166511"}],
            },
            is_error=False,
        )


async def test_call_with_metadata_preserves_full_contract(monkeypatch):
    pool = SourcePool()

    async def fake_get_client(_):
        return FakeClient()

    monkeypatch.setattr(pool, "get_client", fake_get_client)
    raw = await pool.call_with_metadata(
        SOURCES["saos"], "get_judgment",
        {"id": 166511, "offset": 5000, "limit": 5000},
    )
    assert raw["text"] == "Kolejna część uzasadnienia"
    assert raw["structured"]["hasMore"] is True
    assert raw["structured"]["nextOffset"] == 10000
    assert raw["structured"]["citations"][0]["title"] == "V CSK 145/14"
    assert raw["is_error"] is False
