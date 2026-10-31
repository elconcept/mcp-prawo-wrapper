"""Real E2E regression: ELI HTML existence never substitutes the asked-for article."""
from __future__ import annotations

import pytest

from prawo_pl_mcp import slim_resolver as s


@pytest.mark.asyncio
async def test_requested_article_prefers_verified_pdf_even_when_html_exists(monkeypatch):
    monkeypatch.setattr(s, "read_ustawy", lambda *a, **k: None)

    async def no_local(*args, **kwargs):
        return None

    monkeypatch.setattr(s, "_ustawy_mcp_eli", no_local)
    monkeypatch.setattr(s, "_ustawy_mcp_artykul", no_local)
    monkeypatch.setattr(s, "cached_eli_pdf_article", no_local)
    monkeypatch.setattr(s, "read_cache", lambda *a, **k: None)
    monkeypatch.setattr(s, "_odczyt_json", lambda url: {
        "title": "Ustawa", "textHTML": True, "status": "obowiązujący",
    })

    def html_must_not_be_read(*args, **kwargs):
        raise AssertionError("HTML whole-act must not replace exact article")
    monkeypatch.setattr(s, "_odczyt_html", html_must_not_be_read)

    calls = []
    async def pdf(eli, article, page):
        calls.append((eli, article, page))
        return {
            "status": "znaleziony",
            "tekst": "Art. 23. Tekst zweryfikowanego artykułu.",
            "artykul": article,
            "artykul_kompletny": True,
            "dokument_pelny": False,
            "pochodzenie": "fallback_pdf_zapisany_lokalnie",
        }

    monkeypatch.setattr(s, "fetch_eli_pdf_article", pdf)
    result = await s.pobierz_dokument("eli:DU/2024/917", artykul="23")
    assert calls == [("DU/2024/917", "23", 1)]
    assert result["tekst"] == "Art. 23. Tekst zweryfikowanego artykułu."
    assert result["artykul_kompletny"] is True
    assert result["dokument_pelny"] is False


@pytest.mark.asyncio
async def test_article_pdf_failure_must_not_fall_back_to_html(monkeypatch):
    monkeypatch.setattr(s, "read_ustawy", lambda *a, **k: None)

    async def no_local(*args, **kwargs):
        return None

    monkeypatch.setattr(s, "_ustawy_mcp_eli", no_local)
    monkeypatch.setattr(s, "_ustawy_mcp_artykul", no_local)
    monkeypatch.setattr(s, "cached_eli_pdf_article", no_local)
    monkeypatch.setattr(s, "read_cache", lambda *a, **k: None)
    monkeypatch.setattr(s, "_odczyt_json", lambda url: {"textHTML": True})
    monkeypatch.setattr(s, "_odczyt_html", lambda url: (_ for _ in ()).throw(
        AssertionError("HTML may not mask failed PDF verification")
    ))

    async def failed_pdf(*args):
        return {
            "status": "niezweryfikowany_pdf",
            "tekst": "",
            "artykul_kompletny": False,
            "dokument_pelny": False,
        }

    monkeypatch.setattr(s, "fetch_eli_pdf_article", failed_pdf)
    result = await s.pobierz_dokument("eli:DU/2024/917", artykul="23")
    assert result["status"] == "niezweryfikowany_pdf"
    assert result["tekst"] == ""
    assert result["artykul_kompletny"] is False
