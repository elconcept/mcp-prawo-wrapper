"""Kontrakt cache hit i brak zaufania do niepełnego raportu PDF."""
from __future__ import annotations

import hashlib
import pytest

from prawo_pl_mcp import eli_pdf_fallback as e


@pytest.mark.asyncio
async def test_eli_pdf_cache_hit_never_calls_browser(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAWO_RESOLVER_CACHE", str(tmp_path / "eli.sqlite"))
    text = "Art. 23. Zweryfikowany z PDF. " * 12
    from prawo_pl_mcp.local_corpus import save_cache
    assert save_cache(
        "eli:DU/2024/917#art:23#day:2026-10-31", jezyk="pl", tekst=text,
        url="https://api.sejm.gov.pl/eli/acts/DU/2024/917/text.pdf",
        metadane={"źródło": "ELI", "identyfikator": "eli:DU/2024/917",
                  "fidelity_method": "legal-cite-eli2md-pdftotext",
                  "article_verified": True, "na_dzien": "2026-10-31",
                  "pdf_sha256": "f" * 64,
                  "raport_wiernosci": {"wierny_odczyt": True}},
    )
    async def forbidden(*args):
        raise AssertionError("Brak zgody na sieć przy cache HIT")
    monkeypatch.setattr(e, "browser_fallback", forbidden)
    answer = await e.cached_eli_pdf_article("DU/2024/917", "23", 1, "2026-10-31")
    assert answer["pochodzenie"] == "lokalny_cache_pdf"
    assert answer["tekst"] == text
    assert answer["dokument_pelny"] is False
    assert answer["artykul_kompletny"] is True


@pytest.mark.asyncio
async def test_pdf_untrusted_browser_metadata_not_promoted(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAWO_RESOLVER_CACHE", str(tmp_path / "cache.sqlite"))
    async def candidate(*args):
        return {"status": "wierny_odczyt_artykulu_z_pdf",
                "identyfikator": "eli:DU/2024/917", "artykul": "23",
                "dokument_pelny": False, "artykul_kompletny": True,
                "raport": {"wierny_odczyt": True, "monotoniczna_numeracja": True,
                           "silnik": "nieznany", "liczba_trafien_artykulu": 1}}
    monkeypatch.setattr(e, "browser_fallback", candidate)
    r = await e.fetch_eli_pdf_article("DU/2024/917", "23", 1, "2026-10-31")
    assert r["artykul_kompletny"] is False
    assert r["tekst"] == ""


@pytest.mark.asyncio
async def test_eli_verified_worker_artifact_is_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAWO_RESOLVER_CACHE", str(tmp_path / "cache.sqlite"))
    text = "Art. 23. Zweryfikowana treść z PDF. " * 15
    digest = hashlib.sha256(text.encode()).hexdigest()
    folder = tmp_path / "verified"
    folder.mkdir()
    (folder / (digest + ".txt")).write_text(text, encoding="utf-8")
    monkeypatch.setenv("PRAWO_WEBWRIGHT_ARTIFACTS", str(folder))
    async def candidate(tool, args):
        assert tool == "fetch_eli_pdf"
        assert args == {"eli": "DU/2024/917", "artykul": "23",
                        "na_dzien": "2026-10-31"}
        return {"status": "wierny_odczyt_artykulu_z_pdf",
                "identyfikator": "eli:DU/2024/917", "artykul": "23",
                "dokument_pelny": False, "artykul_kompletny": True,
                "adres_pdf": "https://api.sejm.gov.pl/eli/acts/DU/2024/917/text.pdf",
                "artifact_file": digest + ".txt",
                "artifact_sha256": digest, "pdf_sha256": "f" * 64,
                "raport": {"silnik": "legal-cite-pl/pdf_tj.py",
                           "wierny_odczyt": True,
                           "monotoniczna_numeracja": True,
                           "liczba_trafien_artykulu": 1,
                           "wersja_legal_cite": "2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988",
                           "na_dzien": "2026-10-31"}}
    monkeypatch.setattr(e, "browser_fallback", candidate)
    r = await e.fetch_eli_pdf_article("DU/2024/917", "23", 1, "2026-10-31")
    assert r["pochodzenie"] == "fallback_pdf_zapisany_lokalnie"
    assert r["tekst"] == text
    assert r["dokument_pelny"] is False
    hit = await e.cached_eli_pdf_article("DU/2024/917", "23", 1, "2026-10-31")
    assert hit["tekst"] == text
    assert hit["pochodzenie"] == "lokalny_cache_pdf"


@pytest.mark.asyncio
async def test_eli_pdf_cache_is_separated_by_day(tmp_path, monkeypatch):
    from prawo_pl_mcp.local_corpus import save_cache
    monkeypatch.setenv("PRAWO_RESOLVER_CACHE", str(tmp_path / "cache.sqlite"))
    text = "Art. 23. Wierny, ale stan prawny nieustalony. " * 10
    assert save_cache(
        "eli:DU/2024/917#art:23#day:2026-10-30",
        jezyk="pl", tekst=text,
        url="https://api.sejm.gov.pl/eli/acts/DU/2024/917/text.pdf",
        metadane={"źródło": "ELI", "identyfikator": "eli:DU/2024/917",
                  "fidelity_method": "legal-cite-eli2md-pdftotext",
                  "article_verified": True, "na_dzien": "2026-10-30"},
    )
    assert (await e.cached_eli_pdf_article(
        "DU/2024/917", "23", 1, "2026-10-30"
    ))["tekst"] == text
    assert await e.cached_eli_pdf_article(
        "DU/2024/917", "23", 1, "2026-10-31"
    ) is None
