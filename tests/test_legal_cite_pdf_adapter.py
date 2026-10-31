"""Testy adaptera PDF-only legal-cite bez sieci i bez wymagania pakietu.

Testy rzeczywistego eli2md/pdftotext są bramką integracyjną w obrazie workera.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import sys
import types

from prawo_pl_mcp import legal_cite_pdf_adapter as pdf


@dataclass
class FakeUnit:
    klucz: str = "23"
    niejednoznaczne: bool = False
    def czysty(self) -> str:
        return "Art. 23. Tekst odczytany z urzędowego PDF. " * 12


@dataclass
class FakeQC:
    ok: bool = True
    powod: str = ""
    niewyjasnione: list | None = None


def _patch_legal_cite(monkeypatch, *, passed=True, monotonic=True, duplicated=False):
    module = types.ModuleType("legal_cite")
    lc = types.ModuleType("legal_cite.pdf_tj")
    lc.wersja_konwertera = lambda: "eli2md v0.6.70"
    lc.wersja_pdftotext = lambda: "pdftotext test"
    lc._konwertuj = lambda pdf_path, md_path: "# Art. 23\nTekst"
    lc._warstwa = lambda pdf_path, txt_path: "Art. 23. Tekst odczytany z PDF"
    lc.przypisy_md = lambda md: {}
    lc.jednostki_md = lambda md, przypisy, dzis: (
        [FakeUnit()] * (2 if duplicated else 1), monotonic
    )
    lc._tokeny_pdftotext = lambda raw: ["Art", "23", "Tekst"]
    lc.wyjasnienia_warstwy = lambda raw, przypisy, pos: bytearray(len(raw))
    lc.wiernosc_pdftotext = lambda article, raw, mask: FakeQC(
        ok=passed, powod="" if passed else "zgubione słowo", niewyjasnione=[]
    )
    module.pdf_tj = lc
    monkeypatch.setitem(sys.modules, "legal_cite", module)
    monkeypatch.setitem(sys.modules, "legal_cite.pdf_tj", lc)


def test_pdf_two_reader_contract_accepts_one_faithful_article(tmp_path, monkeypatch):
    _patch_legal_cite(monkeypatch)
    data = b"%PDF-1.4\n" + b"TEST" * 200
    result = pdf.przeanalizuj_pdf_eli("DU/2024/917", "23", str(tmp_path), pdf_data=data)
    assert result["status"] == "wierny_odczyt_artykulu_z_pdf"
    assert result["artykul_kompletny"] is True
    assert result["dokument_pelny"] is False
    assert result["tekst_prawnie_nieurzedowy"] is True
    assert result["raport"]["wierny_odczyt"] is True
    assert result["pdf_sha256"] == hashlib.sha256(data).hexdigest()
    assert (tmp_path / result["artifact_pdf"]).read_bytes() == data
    assert (tmp_path / result["artifact_file"]).is_file()
    assert (tmp_path / (result["raport_sha256"] + ".json")).is_file()


def test_pdf_two_reader_contract_rejects_missing_word(tmp_path, monkeypatch):
    _patch_legal_cite(monkeypatch, passed=False)
    r = pdf.przeanalizuj_pdf_eli("DU/2024/917", "23", str(tmp_path), pdf_data=b"%PDF-test")
    assert r["status"] == "rozbieznosc_wiernosci"
    assert r["dokument_pelny"] is False
    assert not list(tmp_path.glob("*.txt"))


def test_pdf_requires_monotonic_unique_article(tmp_path, monkeypatch):
    _patch_legal_cite(monkeypatch, monotonic=False)
    r = pdf.przeanalizuj_pdf_eli("DU/2024/917", "23", str(tmp_path), pdf_data=b"%PDF-test")
    assert r["status"] == "niejednoznaczna_struktura"
    _patch_legal_cite(monkeypatch, duplicated=True)
    r = pdf.przeanalizuj_pdf_eli("DU/2024/917", "23", str(tmp_path), pdf_data=b"%PDF-test")
    assert r["status"] == "niejednoznaczna_struktura"


def test_pdf_invalid_identifier_short_circuits_network(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf, "_get_official_pdf",
                        lambda *a: (_ for _ in ()).throw(AssertionError("no API")))
    assert pdf.przeanalizuj_pdf_eli("DU/2024/xx", "23", str(tmp_path))["status"] == "błędny_id"
    assert pdf.przeanalizuj_pdf_eli("DU/2024/917", "DROP TABLE", str(tmp_path))["status"] == "błędny_artykul"


def test_pdf_adapter_rejects_historical_date_before_download(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf, "_get_official_pdf",
                        lambda *args: (_ for _ in ()).throw(
                            AssertionError("Brak pobierania bez wersji historycznej")))
    result = pdf.przeanalizuj_pdf_eli("DU/2024/917", "23", str(tmp_path),
                                     na_dzien="2025-05-01")
    assert result["status"] == "brak_zweryfikowanego_brzmienia_na_dzien"
    assert result["dokument_pelny"] is False
    assert result["artykul_kompletny"] is False
