"""Kontrakt cache hit i brak zaufania do niepełnego raportu PDF."""
from __future__ import annotations

import hashlib
import json
from datetime import date
import pytest

TODAY = date.today().isoformat()

from prawo_pl_mcp import eli_pdf_fallback as e


def _write_report(folder, report):
    raw = json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    (folder / (digest + ".json")).write_bytes(raw)
    return digest


@pytest.mark.asyncio
async def test_eli_pdf_cache_hit_never_calls_browser(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAWO_RESOLVER_CACHE", str(tmp_path / "eli.sqlite"))
    text = "Art. 23. Zweryfikowany z PDF. " * 12
    from prawo_pl_mcp.local_corpus import save_cache
    folder = tmp_path / "verified"
    folder.mkdir()
    pdf = b"%PDF-1.7\n" + b"RAW PDF" * 100
    pdf_sha = hashlib.sha256(pdf).hexdigest()
    pdf_file = folder / (pdf_sha + ".pdf")
    pdf_file.write_bytes(pdf)
    report = {"silnik": "legal-cite-pl/pdf_tj.py",
              "wersja_legal_cite": "2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988",
              "wierny_odczyt": True, "monotoniczna_numeracja": True,
              "liczba_trafien_artykulu": 1, "na_dzien": TODAY}
    report_sha = _write_report(folder, report)
    monkeypatch.setenv("PRAWO_WEBWRIGHT_ARTIFACTS", str(folder))
    assert save_cache(
        f"eli:DU/2024/917#art:23#day:{TODAY}", jezyk="pl", tekst=text,
        url="https://api.sejm.gov.pl/eli/acts/DU/2024/917/text.pdf",
        metadane={"źródło": "ELI", "identyfikator": "eli:DU/2024/917",
                  "fidelity_method": "legal-cite-eli2md-pdftotext",
                  "article_verified": True, "na_dzien": TODAY,
                  "pdf_sha256": pdf_sha, "raport_sha256": report_sha,
                  "parser_sha": "2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988",
                  "raport_wiernosci": report},
    )
    async def forbidden(*args):
        raise AssertionError("Brak zgody na sieć przy cache HIT")
    monkeypatch.setattr(e, "browser_fallback", forbidden)
    answer = await e.cached_eli_pdf_article("DU/2024/917", "23", 1)
    assert answer["pochodzenie"] == "lokalny_cache_pdf"
    assert answer["tekst"] == text
    assert answer["dokument_pelny"] is False
    assert answer["artykul_kompletny"] is True
    pdf_file.unlink()
    assert await e.cached_eli_pdf_article("DU/2024/917", "23", 1) is None
    pdf_file.write_bytes(pdf)
    (folder / (report_sha + ".json")).write_text('{"tampered": true}', encoding="utf-8")
    assert await e.cached_eli_pdf_article("DU/2024/917", "23", 1) is None


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
    r = await e.fetch_eli_pdf_article("DU/2024/917", "23", 1)
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
    pdf_blob = b"%PDF-1.7\n" + b"TEST" * 200
    pdf_digest = hashlib.sha256(pdf_blob).hexdigest()
    (folder / (pdf_digest + ".pdf")).write_bytes(pdf_blob)
    monkeypatch.setenv("PRAWO_WEBWRIGHT_ARTIFACTS", str(folder))
    report = {"silnik": "legal-cite-pl/pdf_tj.py", "wierny_odczyt": True,
              "monotoniczna_numeracja": True, "liczba_trafien_artykulu": 1,
              "wersja_legal_cite": "2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988",
              "na_dzien": TODAY}
    report_sha = _write_report(folder, report)
    async def candidate(tool, args):
        assert tool == "fetch_eli_pdf"
        assert args == {"eli": "DU/2024/917", "artykul": "23",
                        "na_dzien": None}
        return {"status": "wierny_odczyt_artykulu_z_pdf",
                "identyfikator": "eli:DU/2024/917", "artykul": "23",
                "dokument_pelny": False, "artykul_kompletny": True,
                "adres_pdf": "https://api.sejm.gov.pl/eli/acts/DU/2024/917/text.pdf",
                "artifact_file": digest + ".txt",
                "artifact_sha256": digest, "pdf_sha256": pdf_digest,
                "artifact_pdf": pdf_digest + ".pdf",
                "raport_sha256": report_sha, "raport": report}
    monkeypatch.setattr(e, "browser_fallback", candidate)
    r = await e.fetch_eli_pdf_article("DU/2024/917", "23", 1)
    assert r["pochodzenie"] == "fallback_pdf_zapisany_lokalnie"
    assert r["tekst"] == text
    assert r["dokument_pelny"] is False
    hit = await e.cached_eli_pdf_article("DU/2024/917", "23", 1)
    assert hit["tekst"] == text
    assert hit["pochodzenie"] == "lokalny_cache_pdf"


@pytest.mark.asyncio
async def test_historical_pdf_cache_is_never_treated_as_versioned_law(tmp_path, monkeypatch):
    """Nawet starszy cache opisany #day nie potwierdza stanu historycznego."""
    from prawo_pl_mcp.local_corpus import save_cache
    monkeypatch.setenv("PRAWO_RESOLVER_CACHE", str(tmp_path / "cache.sqlite"))
    past = "2024-10-30"
    text = "Art. 23. Wierny odczyt statycznego PDF, ale bez historii zmian. " * 10
    assert save_cache(
        f"eli:DU/2024/917#art:23#day:{past}", jezyk="pl", tekst=text,
        url="https://api.sejm.gov.pl/eli/acts/DU/2024/917/text.pdf",
        metadane={"źródło": "ELI", "identyfikator": "eli:DU/2024/917",
                  "fidelity_method": "legal-cite-eli2md-pdftotext",
                  "article_verified": True, "na_dzien": past,
                  "pdf_sha256": "f" * 64,
                  "parser_sha": "2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988",
                  "raport_wiernosci": {
                      "silnik": "legal-cite-pl/pdf_tj.py",
                      "wersja_legal_cite": "2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988",
                      "wierny_odczyt": True, "monotoniczna_numeracja": True,
                      "liczba_trafien_artykulu": 1, "na_dzien": past,
                  }},
    )
    assert await e.cached_eli_pdf_article("DU/2024/917", "23", 1, past) is None
    async def forbidden(*args, **kwargs):
        raise AssertionError("Nie wolno uruchomić workera dla stanu historycznego")
    monkeypatch.setattr(e, "browser_fallback", forbidden)
    r = await e.fetch_eli_pdf_article("DU/2024/917", "23", 1, past)
    assert r["status"] == "brak_zweryfikowanego_brzmienia_na_dzien"
    assert r["artykul_kompletny"] is False
    assert r["tekst"] == ""


@pytest.mark.asyncio
async def test_pdf_worker_rejected_when_original_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAWO_RESOLVER_CACHE", str(tmp_path / "cache.sqlite"))
    folder = tmp_path / "verified"
    folder.mkdir()
    monkeypatch.setenv("PRAWO_WEBWRIGHT_ARTIFACTS", str(folder))
    text = "Art. 23. Długi tekst do próby walidacji. " * 12
    text_sha = hashlib.sha256(text.encode()).hexdigest()
    (folder / (text_sha + ".txt")).write_text(text, encoding="utf-8")
    async def candidate(_tool, _args):
        return {
            "status": "wierny_odczyt_artykulu_z_pdf", "identyfikator": "eli:DU/2024/917",
            "artykul": "23", "artykul_kompletny": True, "dokument_pelny": False,
            "adres_pdf": "https://api.sejm.gov.pl/eli/acts/DU/2024/917/text.pdf",
            "artifact_file": text_sha + ".txt", "artifact_sha256": text_sha,
            "artifact_pdf": "f" * 64 + ".pdf", "pdf_sha256": "f" * 64,
            "raport_sha256": "f" * 64,
            "raport": {"silnik": "legal-cite-pl/pdf_tj.py",
                       "wersja_legal_cite": "2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988",
                       "wierny_odczyt": True, "monotoniczna_numeracja": True,
                       "liczba_trafien_artykulu": 1, "na_dzien": TODAY},
        }
    monkeypatch.setattr(e, "browser_fallback", candidate)
    result = await e.fetch_eli_pdf_article("DU/2024/917", "23", 1)
    assert result["status"] == "błąd_integralności"
    assert result["dokument_pelny"] is False
    assert await e.cached_eli_pdf_article("DU/2024/917", "23", 1) is None
