"""Regresja local-first: dokładne ELI, integralność cache, zapis fragmentów.

Żaden test nie łączy się z siecią i nie zapisuje do produkcyjnego USTAWY.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

from prawo_pl_mcp import local_corpus as l


def _ustawy_fixture(path: Path):
    with sqlite3.connect(path) as c:
        c.executescript("""
          CREATE TABLE akty (akt TEXT PRIMARY KEY, tytul TEXT, eli TEXT,
                            stan_na TEXT, tekst_jednolity TEXT, zrodlo TEXT);
          CREATE TABLE artykuly (akt TEXT, art TEXT, jednostka TEXT, brzmienie TEXT,
                                 PRIMARY KEY(akt, art));
          INSERT INTO akty VALUES ('uozp', 'Ustawa o ochronie zdrowia psychicznego',
                                 'DU/2024/917', '2024-06-21',
                                 'Dz.U. 2024 poz. 917', 'komentarz');
          INSERT INTO artykuly VALUES ('uozp','23','Rozdział 3',
                    'Art. 23. Osoba chora psychicznie może być przyjęta...');
          INSERT INTO artykuly VALUES ('uozp','24','Rozdział 3',
                    'Art. 24. Przyjęcie na obserwację...');
        """)


def test_ustawy_matches_exact_eli_readonly(tmp_path):
    source = tmp_path / "ustawy.sqlite"
    _ustawy_fixture(source)
    d = l.read_ustawy("DU/2024/917", "23", path=str(source))
    assert d["zrodlo"] == "komentarz"
    assert d["tryb"] == "ustawy_sqlite"
    assert "Art. 23" in d["tekst"]
    assert "Art. 24" not in d["tekst"]
    assert d["dokument_pelny"] is False
    assert l.read_ustawy("DU/2025/917", "23", path=str(source)) is None
    assert l.read_ustawy("DU/2024/917", "300", path=str(source)) is None
    full = l.read_ustawy("DU/2024/917", path=str(source))
    assert "Art. 24" in full["tekst"] and not full["dokument_pelny"]


def test_cache_only_full_verified_text_and_sha(tmp_path):
    file = str(tmp_path / "resolver.sqlite")
    ident = "eli:DU/2024/917"
    text = "Oficjalnie pobrany tekst ogłoszenia. " * 25
    assert not l.save_cache(ident, jezyk="pl", tekst="fragment", url="https://api.sejm.gov.pl/x",
                            metadane={"źródło": "ELI"}, path=file)
    assert not l.save_cache(ident, jezyk="en", tekst=text, url="https://api.sejm.gov.pl/x",
                            metadane={"źródło": "ELI"}, path=file)
    assert not l.save_cache(ident, jezyk="pl", tekst=text, url="https://api.sejm.gov.pl/x",
                            metadane={"źródło": "ELI"}, kompletny=False, path=file)
    assert l.save_cache(ident, jezyk="pl", tekst=text, url="https://api.sejm.gov.pl/x",
                        metadane={"źródło": "ELI"}, path=file)
    row = l.read_cache(ident, path=file)
    assert row["tekst"] == text
    assert row["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert row["metadane"]["źródło"] == "ELI"
    with sqlite3.connect(file) as c:
        c.execute("UPDATE documents SET tekst='MANIPULACJA' WHERE identyfikator=?", (ident,))
    assert l.read_cache(ident, path=file) is None


def test_native_fragments_cached_without_false_full_claim(tmp_path, monkeypatch):
    file = str(tmp_path / "resolver.sqlite")
    monkeypatch.setenv(l.CACHE_DB_ENV, file)
    ident = "saos:166511"
    meta = {"offset": 0, "totalLength": 9900, "returnedLength": 5000,
            "nextOffset": 5000, "hasMore": True,
            "citations": [{"title": "V CSK 145/14"}]}
    assert l.save_fragment(ident, 0, 5000, "S" * 5000, meta)
    assert not l.save_fragment(ident, 0, 5000, "S" * 4999, meta)
    row = l.read_fragment(ident, 0, 5000)
    assert row["total_length"] == 9900
    assert row["returned_length"] == 5000
    assert row["citations"][0]["title"] == "V CSK 145/14"
    assert l.read_fragment(ident, 5000, 5000) is None
    assert not l.save_fragment(ident, 0, 5000, "zły", {**meta, "nextOffset": 9000})
    l.record_candidate("celex:32016R0679:pl", {"status": "kandydat_zapisany", "url": "https://eur-lex.europa.eu"})
    with sqlite3.connect(file) as c:
        x = c.execute("SELECT status FROM candidates WHERE identyfikator=?", ("celex:32016R0679:pl",)).fetchone()
        assert x[0] == "kandydat_zapisany"


def test_eu_pl_is_never_read_from_english_corpus(tmp_path, monkeypatch):
    path = str(tmp_path / "eu_pl.sqlite")
    monkeypatch.setenv(l.EU_PL_DB_ENV, path)
    text = "Zgłaszanie naruszenia ochrony danych osobowych. " * 20
    assert l.save_cache("celex:32016R0679:pl", jezyk="pl", tekst=text,
                        url="https://eur-lex.europa.eu/legal-content/PL/TXT/",
                        metadane={"źródło": "EUR-Lex", "wersja_urzedowa_pl": False}, path=path)
    assert l.read_eu_pl("32016R0679") is None
    assert l.save_cache("celex:32016R0679:pl", jezyk="pl", tekst=text,
                        url="https://eur-lex.europa.eu/legal-content/PL/TXT/",
                        metadane={"źródło": "EUR-Lex", "wersja_urzedowa_pl": True}, path=path)
    assert l.read_eu_pl("32016R0679")["tekst"] == text
