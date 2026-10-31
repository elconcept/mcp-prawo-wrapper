"""PDF: walidacja oficjalnych źródeł bez połączeń sieciowych."""
import hashlib
from pathlib import Path
import pytest

from prawo_pl_mcp import pdf_ingest as p


def test_urzedowa_tozsamosc_pdf():
    gdpr = ("ROZPORZĄDZENIE PARLAMENTU EUROPEJSKIEGO I RADY (UE) 2016/679\n"
            "Artykuł 33. Zgłaszanie naruszenia ochrony danych osobowych.\n") * 30
    assert p._verified_identity(gdpr, source="eurlex", identity="32016R0679")
    assert not p._verified_identity(gdpr, source="eurlex", identity="32024R1689")
    assert not p._verified_identity(gdpr, source="sn", identity="III CZP 1/24")
    sn = ("Sąd Najwyższy, sygn. III CZP 1/24. Uzasadnienie.\n") * 40
    assert p._verified_identity(sn, source="sn", identity="III CZP 1/24")
    assert not p._verified_identity(sn, source="sn", identity="III CZP 2/24")


def test_niedozwolone_hosty_i_jezyk_pdf():
    with pytest.raises(ValueError):
        p._get_official_pdf("https://127.0.0.1/sekret.pdf", "sn")
    with pytest.raises(ValueError):
        p._get_official_pdf("https://sn.pl.evil.example/dokument.pdf", "sn")
    with pytest.raises(ValueError):
        p._get_official_pdf("http://www.sn.pl/w.pdf", "sn")
    with pytest.raises(ValueError):
        p._get_official_pdf("https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/RODO", "eurlex")


def test_import_pdf_weryfikuje_przed_zapisem(tmp_path, monkeypatch):
    blob = b"%PDF-1.4\nSztuczny tekst PDF testowego mocka"
    text = ("ROZPORZĄDZENIE (UE) 2016/679. Artykuł 33.\n" * 80)
    monkeypatch.setattr(p, "_get_official_pdf", lambda url, source: blob)
    monkeypatch.setattr(p, "_pdf_text", lambda blob: (text, 2))
    r = p.ingest_verified_pdf(
        "https://eur-lex.europa.eu/legal-content/PL/TXT/PDF/?uri=CELEX:32016R0679",
        source="eurlex", identity="32016R0679", directory=str(tmp_path))
    assert r["status"] == "kandydat_pdf_zapisany"
    assert r["dokument_pelny"] is False
    assert r["wynik_wiernosci"] == "niezweryfikowany"
    assert (tmp_path / r["artifact_file"]).read_text(encoding="utf-8") == text
    assert r["artifact_sha256"] == hashlib.sha256(text.encode()).hexdigest()


def test_dokument_z_innym_id_nie_przechodzi(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "_get_official_pdf", lambda url, source: b"%PDF-1.4\n")
    monkeypatch.setattr(p, "_pdf_text", lambda blob: ("INNY DOKUMENT " * 200, 1))
    r = p.ingest_verified_pdf("https://www.sn.pl/doc.pdf", source="sn",
                              identity="III CZP 1/24", directory=str(tmp_path))
    assert r["status"] == "nieweryfikowalny_pdf"
    assert list(tmp_path.iterdir()) == []
