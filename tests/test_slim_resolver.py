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
    assert result["status"] == "niezweryfikowana_kompletność"
    assert result["dalszy_fragment"] is None
    assert result["dokument_pelny"] is False


@pytest.mark.asyncio
async def test_saos_przekazuje_cytowania_i_natywny_has_more(monkeypatch):
    class FakePool:
        async def call_with_metadata(self, src, tool, args):
            assert args == {"id": 166511, "offset": 0, "limit": 5000}
            return {"text": "Pełny fragment", "structured": {
                "totalLength": 11000, "hasMore": True, "nextOffset": 5000,
                "citations": [{"title": "V CSK 145/14"}]}, "is_error": False}

    monkeypatch.setattr(s, "POOL", FakePool())
    result = await s._orzeczenie("saos", "166511", 1)
    assert result["dalszy_fragment"] is True
    assert result["kolejna_strona"] == 2
    assert result["citations"][0]["title"] == "V CSK 145/14"


@pytest.mark.asyncio
async def test_celex_nie_podmienia_angielskiego_snapshotu():
    result = await s.pobierz_dokument("RODO art. 33")
    assert result["status"] == "tylko_link"
    assert "/PL/TXT/" in result["adres_urzedowy"]
    assert result["artykul"] == "33"
    assert result["dokument_pelny"] is False
