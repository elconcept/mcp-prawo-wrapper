"""Bezpieczne połączenie resolvera z wewnętrznym legal-cite PDF workerem.

Tylko artykuł, po zweryfikowanej dwuczytnikowo ekstrakcji.
Dla pozostałych przypadków odpowiedź jawnie wskazuje status kandydata.
"""
from __future__ import annotations

import asyncio
from datetime import date
import re

from .browser_bridge import browser_fallback
from .local_corpus import read_cache, save_cache, load_verified_artifact

PAGE_CHARS = 5000


def _key(eli: str, article: str, na_dzien: str | None = None) -> str:
    art = article.strip().lower().replace("^", "_")
    if not re.fullmatch(r"\d{1,4}(?:_[0-9]{1,3}[a-z]?|[a-z]{1,3})?", art):
        raise ValueError("Nieprawidłowy artykuł")
    day = date.fromisoformat(na_dzien) if na_dzien else date.today()
    return f"eli:{eli}#art:{art}#day:{day.isoformat()}"


def _page(text: str, page: int) -> dict:
    offset = (page - 1) * PAGE_CHARS
    fragment = text[offset:offset + PAGE_CHARS]
    has_more = offset + len(fragment) < len(text)
    return {"status": "znaleziony" if offset < len(text) else "poza_zakresem",
            "tekst": fragment, "strona": page,
            "total_chars": len(text), "dalszy_fragment": has_more,
            "kolejna_strona": page + 1 if has_more else None}


async def cached_eli_pdf_article(eli: str, article: str, page: int,
                                 na_dzien: str | None = None) -> dict | None:
    try:
        key = _key(eli, article, na_dzien)
        cached = await asyncio.to_thread(read_cache, key)
    except (ValueError, OSError):
        return None
    if not cached or not cached["kompletny"]:
        return None
    meta = cached["metadane"]
    if (meta.get("fidelity_method") != "legal-cite-eli2md-pdftotext"
            or meta.get("article_verified") is not True
            or meta.get("identyfikator") != "eli:" + eli
            or meta.get("na_dzien") != key.split("#day:")[1]):
        return None
    return {
        "identyfikator": "eli:" + eli,
        "artykul": article, "dokument_pelny": False, "artykul_kompletny": True,
        "zrodlo": "urzędowy PDF ELI; nieurzędowy odczyt artykułu",
        "pochodzenie": "lokalny_cache_pdf",
        "adres_pdf": cached["adres_zrodlowy"],
        "sha256": cached["sha256"], "pdf_sha256": meta.get("pdf_sha256"),
        "stan_prawny_na": meta.get("na_dzien"),
        "aktualnosc_prawna": "niezweryfikowana",
        "raport_wiernosci": meta.get("raport_wiernosci"),
    } | _page(cached["tekst"], page)


async def fetch_eli_pdf_article(eli: str, article: str, page: int,
                                na_dzien: str | None = None) -> dict:
    """Akceptuje wyłącznie wynik z legal-cite (kolejność słów + brak pominięć).

    Nie udaje pełnego oryginalnego Dz.U.; pełna publikacja może mieć załączniki.
    """
    expected_id = "eli:" + eli
    try:
        key = _key(eli, article, na_dzien)
    except ValueError:
        return {"status": "błędny_artykul", "identyfikator": expected_id,
                "dokument_pelny": False}
    result = await browser_fallback(
        "fetch_eli_pdf", {"eli": eli, "artykul": article, "na_dzien": key.split("#day:")[1]}
    )
    raw = result.get("raport")
    if (result.get("status") != "wierny_odczyt_artykulu_z_pdf"
            or result.get("identyfikator") != expected_id
            or result.get("artykul") != key.split("#art:")[1]
            or result.get("artykul_kompletny") is not True
            or result.get("dokument_pelny") is not False
            or not isinstance(raw, dict)
            or raw.get("wierny_odczyt") is not True
            or raw.get("monotoniczna_numeracja") is not True
            or raw.get("liczba_trafien_artykulu") != 1
            or raw.get("silnik") != "legal-cite-pl/pdf_tj.py"
            or raw.get("na_dzien") != key.split("#day:")[1]):
        return {"status": result.get("status", "niezweryfikowany_pdf"),
                "identyfikator": expected_id,
                "artykul": article, "dokument_pelny": False, "artykul_kompletny": False,
                "tekst": "", "adres_pdf": f"https://api.sejm.gov.pl/eli/acts/{eli}/text.pdf",
                "uwaga": "Nie ma pełnego raportu wierności PDF; dokument pozostaje kandydatem."}
    expected_url = f"https://api.sejm.gov.pl/eli/acts/{eli}/text.pdf"
    if result.get("adres_pdf") != expected_url:
        return {"status": "błąd_pochodzenia", "dokument_pelny": False, "tekst": ""}
    try:
        text = await asyncio.to_thread(
            load_verified_artifact, result["artifact_file"], result["artifact_sha256"]
        )
        if len(text.strip()) < 100:
            raise ValueError("Niewiarygodnie krótki artykuł")
        saved = await asyncio.to_thread(
            save_cache, key, jezyk="pl", tekst=text, url=expected_url,
            metadane={
                "źródło": "ELI PDF Kancelarii Sejmu",
                "identyfikator": expected_id,
                "artykul": article,
                "fidelity_method": "legal-cite-eli2md-pdftotext",
                "article_verified": True,
                "pdf_sha256": result.get("pdf_sha256"),
                "na_dzien": key.split("#day:")[1],
                "raport_wiernosci": raw,
                "parser_sha": raw.get("wersja_legal_cite"),
            },
        )
    except (ValueError, OSError, KeyError):
        return {"status": "błąd_integralności", "identyfikator": expected_id,
                "dokument_pelny": False, "tekst": ""}
    if not saved:
        return {"status": "błąd_cache", "identyfikator": expected_id,
                "dokument_pelny": False, "tekst": ""}
    return {
        "identyfikator": expected_id, "artykul": article,
        "dokument_pelny": False, "artykul_kompletny": True,
        "zrodlo": "urzędowy PDF ELI; nieurzędowy odczyt artykułu",
        "pochodzenie": "fallback_pdf_zapisany_lokalnie",
        "adres_pdf": expected_url, "pdf_sha256": result.get("pdf_sha256"),
        "aktualnosc_prawna": "niezweryfikowana",
        "stan_prawny_na": raw.get("na_dzien"),
        "raport_wiernosci": raw,
    } | _page(text, page)
