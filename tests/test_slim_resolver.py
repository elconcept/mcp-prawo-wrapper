"""Bez sieci: parsowanie identyfikatorów i kompletność odpowiedzi resolvera."""
from __future__ import annotations

import pytest

from prawo_pl_mcp import slim_resolver as s


@pytest.mark.parametrize(("raw", "expected"), [
    ("eli:DU/2024/917", ("eli", "DU/2024/917", None)),
    ("DU/2024/917", ("eli", "DU/2024/917", None)),
    ("Dz.U. 2024 poz. 917", ("eli", "DU/2024/917", None)),
    ("M.P. z 2026 r. poz. 100", ("eli", "MP/2026/100", None)),
    ("nsa:389f2c5b67", ("nsa", "389F2C5B67", None)),
    ("saos:166511", ("saos", "166511", None)),
    ("celex:32016R0679:pl", ("celex", "32016R0679", None)),
    ("RODO art. 33", ("celex", "32016R0679", "33")),
    ("eureka:646788", ("eureka", "646788", None)),
    ("sn:hFvgRJcBZvGrB8P_afyJ", ("sn", "hFvgRJcBZvGrB8P_afyJ", None)),
    ("edpb:binding-decision-12026-on-the-dispute-submitted-by-the-belgian-sa:pl",
     ("edpb", "binding-decision-12026-on-the-dispute-submitted-by-the-belgian-sa", None)),
])
def test_id_rozpoznawanie(raw, expected):
    assert s.rozpoznaj(raw) == expected


def test_link_nie_moze_byc_ssrf():
    assert s.bezpieczny_adres("https://www.sn.pl/pl/wyszukiwarka-orzeczen", "sn")
    assert s.bezpieczny_adres("https://www.sn.pl.evil.example/", "sn") is None
    assert s.bezpieczny_adres("https://127.0.0.1/", "sn") is None
    assert s.bezpieczny_adres("http://www.sn.pl/", "sn") is None
    assert s.bezpieczny_adres("https://x:password@www.sn.pl/", "sn") is None
    assert s.bezpieczny_adres("https://www.edpb.europa.eu/file.pdf", "edpb")


def test_stronicowanie_bez_luk():
    text = "a" * 11001
    pages = [s.stronicuj(text, i) for i in (1, 2, 3)]
    assert "".join(x["tekst"] for x in pages) == text
    assert [x["dalszy_fragment"] for x in pages] == [True, True, False]
    assert pages[-1]["kolejna_strona"] is None
    assert s.stronicuj(text, 4)["status"] == "poza_zakresem"


@pytest.mark.asyncio
async def test_eli_z_oficjalnymi_metadanymi_i_stronami(monkeypatch):
    monkeypatch.setattr(s, "_odczyt_json", lambda url: {
        "title": "Jednolity tekst ustawy", "textHTML": True, "status": "obowiązujący",
        "legalStatusDate": "2024-06-13", "references": {
            "Nowelizacje po tekście jednolitym": [{"id": "DU/2025/1"}],
        },
    })
    monkeypatch.setattr(s, "_odczyt_html", lambda url: "T" * 9900)
    result = await s.pobierz_dokument("eli:DU/2024/917", strona=1)
    assert result["status"] == "znaleziony"
    assert result["dalszy_fragment"] is True
    assert result["kolejna_strona"] == 2
    assert result["stan_prawny_na"] == "2024-06-13"
    assert result["zmiany_po_tekście"] == [{"id": "DU/2025/1"}]
    assert result["adres_urzedowy"] == "https://api.sejm.gov.pl/eli/acts/DU/2024/917"


@pytest.mark.asyncio
async def test_nsa_brak_metadanych_nie_oznacza_kompletnego_tekstu(monkeypatch):
    class FakePool:
        async def call_with_metadata(self, src, tool, args):
            assert tool == "get_judgment"
            assert args["offset"] == 5000
            return {"text": "Tylko nagłówek i początek", "structured": {}, "is_error": False}

    monkeypatch.setattr(s, "POOL", FakePool())
    result = await s._orzeczenie("nsa", "389F2C5B67", 2)
    assert result["status"] == "niezweryfikowany_fragment"
    assert result["dalszy_fragment"] is None
    assert result["dokument_pelny"] is False


@pytest.mark.asyncio
async def test_saos_przekazuje_cytowania_i_natywny_has_more(monkeypatch):
    class FakePool:
        async def call_with_metadata(self, src, tool, args):
            assert args == {"id": 166511, "offset": 0, "limit": 5000}
            return {"text": "S" * 5000, "structured": {
                "totalLength": 11000, "returnedLength": 5000,
                "offset": 0, "hasMore": True, "nextOffset": 5000,
                "citations": [{"title": "V CSK 145/14"}]}, "is_error": False}

    monkeypatch.setattr(s, "POOL", FakePool())
    result = await s._orzeczenie("saos", "166511", 1)
    assert result["dalszy_fragment"] is True
    assert result["kolejna_strona"] == 2
    assert result["citations"][0]["title"] == "V CSK 145/14"


@pytest.mark.asyncio
async def test_celex_nie_podmienia_angielskiego_snapshotu():
    result = await s.pobierz_dokument("RODO art. 33")
    assert result["status"] in ("tylko_link", "niepodłączony_webwright", "błąd_źródła")
    assert "/PL/TXT/" in result["adres_urzedowy"]
    assert result["artykul"] == "33"
    assert result["dokument_pelny"] is False


@pytest.mark.asyncio
async def test_eli_z_lokalnych_ustaw_bez_dotykania_api(monkeypatch):
    calls = []

    def fake_local(eli, art):
        calls.append(("ustawy", eli, art))
        return {
            "tekst": "Art. 23. Tekst z lokalnego USTAWY.",
            "identyfikator": "eli:DU/2024/917",
            "tytul": "Ustawa o ochronie zdrowia psychicznego",
            "adres_urzedowy": "https://api.sejm.gov.pl/eli/acts/DU/2024/917",
            "uwaga": "Stan brzmienia: tekst jednolity.",
            "dokument_pelny": False,
        }

    def forbidden_api(url):
        raise AssertionError("Nie wolno wywołać API Sejmu przy trafieniu w USTAWY")

    monkeypatch.setattr(s, "read_ustawy", fake_local)
    monkeypatch.setattr(s, "_odczyt_json", forbidden_api)
    result = await s.pobierz_dokument("Dz.U. 2024 poz. 917", artykul="23")
    assert result["pochodzenie"] == "lokalny_ustawy"
    assert result["tekst"].startswith("Art. 23")
    assert result["dokument_pelny"] is False
    assert calls == [("ustawy", "DU/2024/917", "23")]


@pytest.mark.asyncio
async def test_celex_z_lokalnego_polskiego_korpusu_bez_przegladarki(monkeypatch):
    async def forbidden_browser(*args, **kwargs):
        raise AssertionError("Przeglądarka nie powinna ruszać przy cache hit")

    monkeypatch.setattr(s, "read_eu_pl", lambda celex, art: {
        "tekst": "Rozporządzenie (UE) 2016/679. Artykuł 33. " * 100,
        "adres_zrodlowy": "https://eur-lex.europa.eu/legal-content/PL/TXT/",
        "pobrano_at": "2026-10-31T00:00:00+00:00",
        "sha256": "abc",
    })
    monkeypatch.setattr(s, "browser_fallback", forbidden_browser)
    result = await s.pobierz_dokument("RODO art. 33")
    assert result["pochodzenie"] == "lokalny_eu_pl"
    assert result["status"] == "znaleziony"
    assert result["artykul"] == "33"
    assert result["dalszy_fragment"] is False


@pytest.mark.asyncio
async def test_webwright_pdf_bez_zaufanego_parsera_nie_trafia_do_local_cache(monkeypatch):
    digest = "a" * 64
    candidate = {
        "status": "zweryfikowany_tekst_zapisany",
        "zweryfikowany_tekst_urzedowy": True,
        "dokument_pelny": True,
        "adres_pdf": "https://eur-lex.europa.eu/legal-content/PL/TXT/PDF/?uri=CELEX:32016R0679",
        "artifact_file": digest + ".txt", "artifact_sha256": digest,
    }
    monkeypatch.setattr(s, "load_verified_artifact", lambda filename, sha: "Urzędowy tekst " * 100)
    stored = []
    def save(*args, **kwargs):
        stored.append((args, kwargs))
        return True
    monkeypatch.setattr(s, "save_cache", save)
    result = await s._promuj_pdf(candidate, "celex:32016R0679:pl", "celex", 1, "33")
    assert result is None
    assert stored == []
