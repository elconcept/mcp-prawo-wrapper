"""Wewnętrzny MCP Playwright: uruchamia wyłącznie dwa skrypty Apache-2.0.

Żadne narzędzie tej usługi nie powinno trafiać do publicznego katalogu lex.
Usługa jest adapterem fallback, nie niezależną wyszukiwarką.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from .pdf_ingest import ingest_verified_pdf
from .legal_cite_pdf_adapter import przeanalizuj_pdf_eli

BASE = Path(__file__).resolve().parents[2] / "vendor" / "webwright_legal_pl"
OUT = Path(os.environ.get("WEBWRIGHT_DATA_DIR", "/data/webwright"))
SEM = asyncio.Semaphore(1)
RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                     idempotentHint=True, openWorldHint=True)
mcp = FastMCP(
    name="webwright-legal-pl-internal",
    instructions="Wewnętrzny fallback dla resolvera prawa. Obecnie obsługuje "
                 "SN i EUR-Lex PL przez Playwright. MS i TK wymagają "
                 "osobnych, zweryfikowanych adapterów. Wyniki obecnych "
                 "skryptów NIE SĄ automatycznie pełnymi orzeczeniami.",
)


def safe_signature(value: str) -> bool:
    return isinstance(value, str) and bool(
        re.fullmatch(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9 /.,()\-]{4,85}", value)
    ) and ".." not in value


async def _run(script: Path, args: list[str]) -> tuple[int, str]:
    # Brak shell=True; użytkownik nie może wybrać skryptu ani komendy.
    async with SEM:
        p = await asyncio.create_subprocess_exec(
            sys.executable, str(script), *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(p.communicate(), timeout=150)
        except asyncio.TimeoutError:
            p.kill()
            await p.communicate()
            return 2, "Przekroczono czas pracy przeglądarki"
    return p.returncode or 0, stderr.decode("utf-8", errors="replace")[-700:]


def _read_result(folder: Path, filename: str) -> tuple[dict, str]:
    if not folder.resolve().is_relative_to(OUT.resolve()):
        raise ValueError("Ścieżka wyniku poza katalogiem danych")
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    text = (folder / filename).read_text(encoding="utf-8")
    if len(text.encode("utf-8")) > 10_000_000:
        raise ValueError("Przekroczono limit wyniku Playwright")
    return meta, text


async def fetch_celex_pl(celex: str) -> dict:
    """Pobierz kandydata polskiego dokumentu CELEX z EUR-Lex.

    Wstępny skrypt zapisuje cały tekst strony przeglądarki (również nawigację),
    dlatego dopóki walidator nie wydzieli autentycznego tekstu dokumentu,
    odpowiedź NIE oznacza pełnego tekstu urzędowego.
    """
    if not isinstance(celex, str) or not re.fullmatch(r"[0-9A-Z()/\-]{10,30}", celex, re.I):
        return {"status": "błędny_id", "uwaga": "Nieprawidłowy CELEX"}
    celex = celex.upper()
    script = BASE / "scripts" / "fetch_eurlex.py"
    outdir = OUT / "eurlex"
    code, error = await _run(script, ["--celex", celex, "--lang", "PL", "--out", str(outdir)])
    if code != 0:
        return {"status": "błąd_źródła", "identyfikator": "celex:" + celex + ":pl",
                "uwaga": "Nie udało się pobrać danych: " + error}
    try:
        meta, text = _read_result(outdir / celex, "akt.md")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "błąd_weryfikacji", "uwaga": type(exc).__name__}
    url = meta.get("url", "")
    if (meta.get("celex") != celex or meta.get("jezyk") != "PL"
            or urlparse(url).hostname != "eur-lex.europa.eu"):
        return {"status": "błąd_weryfikacji", "uwaga": "Niezgodne metadane CELEX/języka"}
    if meta.get("pdf_url"):
        try:
            verified = await asyncio.to_thread(
                ingest_verified_pdf, meta["pdf_url"], source="eurlex",
                identity=celex, directory=str(OUT / "verified")
            )
            if verified.get("status") == "kandydat_pdf_zapisany":
                return {**verified, "identyfikator": "celex:" + celex + ":pl",
                        "tytul": meta.get("tytul"), "adres_urzedowy": url,
                        "pobrano_at": meta.get("pobrano_at"),
                        "jezyk": "PL", "zweryfikowany_tekst_urzedowy": False,
                        "dokument_pelny": False}
        except Exception:
            pass  # HTML i metadane pozostają kandydatem; nie podawaj pełnego tekstu.
    return {"status": "kandydat_zapisany", "identyfikator": "celex:" + celex + ":pl",
            "tytul": meta.get("tytul"), "adres_urzedowy": url,
            "pdf_url": meta.get("pdf_url"), "pobrano_at": meta.get("pobrano_at"),
            "data_publikacji": meta.get("data_publikacji"),
            "liczba_znakow_strony": len(text),
            "zweryfikowany_tekst_urzedowy": False,
            "dokument_pelny": False,
            "uwaga": "Zapisano lokalny kandydat HTML + metadane i screenshot. "
                     "Cała strona zawiera także nawigację; wymaga walidacji "
                     "tekstu aktu przed przyjęciem do polskiego korpusu."}


async def fetch_orzeczenie_po_sygnaturze(sygnatura: str, zrodlo: str = "sn") -> dict:
    """Wewnętrzny Playwright po sygnaturze: SN działa jako prototyp.

    Adaptery MS i TK NIE są jeszcze w pakiecie źródłowym Webwright.
    """
    if not safe_signature(sygnatura):
        return {"status": "błędna_sygnatura"}
    if zrodlo not in ("sn", "ms", "tk"):
        return {"status": "nieobsługiwane_źródło"}
    if zrodlo != "sn":
        return {"status": "adapter_niegotowy",
                "uwaga": "Dostępny skill ma selektory tylko SN; "
                         "MS i TK wymagają osobnych testów i parserów."}
    script = BASE / "scripts" / "fetch_orzeczenie.py"
    outdir = OUT / "orzeczenia"
    code, error = await _run(script, ["--sygnatura", sygnatura, "--out", str(outdir)])
    if code != 0:
        return {"status": "nie_znaleziono" if code == 1 else "błąd_źródła",
                "uwaga": error}
    # Skrypt źródłowy wyznacza slug po normalizacji sygnatury.
    # Nie odgadujemy ścieżki: wybieramy tylko ostatni katalog z meta o ścisłej sygnaturze.
    try:
        dirs = sorted((p for p in outdir.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
        for folder in dirs[:25]:
            try:
                meta, text = _read_result(folder, "orzeczenie.md")
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if meta.get("sygnatura", "").casefold() == sygnatura.casefold() and meta.get("zrodlo"):
                url = meta.get("url", "")
                if urlparse(url).hostname not in ("sn.pl", "www.sn.pl"):
                    return {"status": "błąd_weryfikacji", "uwaga": "Niepoprawny host SN"}
                if meta.get("pdf_url"):
                    try:
                        verified = await asyncio.to_thread(
                            ingest_verified_pdf, meta["pdf_url"], source="sn",
                            identity=sygnatura, directory=str(OUT / "verified")
                        )
                        if verified.get("status") == "kandydat_pdf_zapisany":
                            return {**verified, "sygnatura": sygnatura,
                                    "typ": meta.get("typ"), "data": meta.get("data"),
                                    "adres_urzedowy": url,
                                    "pobrano_at": meta.get("pobrano_at"),
                                    "zweryfikowany_tekst_urzedowy": False,
                                    "dokument_pelny": False}
                    except Exception:
                        pass
                return {"status": "kandydat_zapisany",
                        "sygnatura": sygnatura, "typ": meta.get("typ"),
                        "data": meta.get("data"), "url": url,
                        "pdf_url": meta.get("pdf_url"),
                        "pobrano_at": meta.get("pobrano_at"),
                        "liczba_znakow_strony": len(text),
                        "dokument_pelny": False,
                        "uwaga": "Zapisano stronę detalu i adres PDF. "
                                 "Pełny tekst PDF nie został jeszcze pobrany ani zweryfikowany."}
    except OSError:
        pass
    return {"status": "błąd_weryfikacji", "uwaga": "Nie znaleziono zgodnych artefaktów"}


async def fetch_eli_pdf(eli: str, artykul: str, na_dzien: str | None = None) -> dict:
    """Wewnętrzny fallback PDF-only ELI: legal-cite eli2md + pdftotext.

    Działa tylko dla konkretnego artykułu. Przy niejednoznaczności nie
    przyznaje statusu wierności i nie dostarcza tekstu do publicznego cache.
    """
    async with SEM:
        try:
            return await asyncio.to_thread(
                przeanalizuj_pdf_eli, eli, artykul, str(OUT / "verified"),
                na_dzien=na_dzien
            )
        except Exception as exc:
            return {"status": "błąd_źródła", "identyfikator": "eli:" + str(eli),
                    "dokument_pelny": False,
                    "uwaga": f"Odczyt PDF ELI nie powiódł się: {type(exc).__name__}"}


mcp.tool(fetch_celex_pl, annotations=RO)
mcp.tool(fetch_eli_pdf, annotations=RO)
mcp.tool(fetch_orzeczenie_po_sygnaturze, annotations=RO)


def main() -> None:
    mcp.run()
