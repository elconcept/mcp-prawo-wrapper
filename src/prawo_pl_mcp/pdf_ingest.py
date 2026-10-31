"""Bezpieczny import urzędowego PDF z whitelisty do lokalnego korpusu.

Brak OCR i obchodzenia ograniczeń serwisu. PDF bez wyodrębnialnego
tekstu lub bez potwierdzenia identyfikatora pozostaje kandydatem.
"""
from __future__ import annotations

from io import BytesIO
import hashlib
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler

MAX_PDF = 20_000_000
MAX_PAGES = 600
MAX_TEXT = 20_000_000

class _OnlyOfficialRedirects(HTTPRedirectHandler):
    def __init__(self, allow: set[str]):
        self.allow = allow
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urlparse(newurl)
        if u.scheme != "https" or u.hostname not in self.allow or u.username or u.password:
            raise ValueError("Przekierowanie PDF do niezaufanego hosta")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _get_official_pdf(url: str, source: str) -> bytes:
    trusted = {
        "sn": {"sn.pl", "www.sn.pl"},
        "eurlex": {"eur-lex.europa.eu", "www.eur-lex.europa.eu"},
    }
    hosts = trusted[source]
    u = urlparse(url)
    if u.scheme != "https" or u.hostname not in hosts or u.username or u.password:
        raise ValueError("PDF musi pochodzić z oficjalnej domeny")
    if source == "eurlex" and "/PL/" not in u.path:
        raise ValueError("Wymagana polska wersja PDF")
    opener = build_opener(_OnlyOfficialRedirects(hosts))
    with opener.open(Request(url, headers={"Accept": "application/pdf"}),
                     timeout=35) as response:
        if urlparse(response.geturl()).hostname not in hosts:
            raise ValueError("Nieoczekiwana domena końcowa PDF")
        b = response.read(MAX_PDF + 1)
    if len(b) > MAX_PDF or not b.startswith(b"%PDF-"):
        raise ValueError("Niepoprawny lub zbyt duży plik PDF")
    return b


def _pdf_text(blob: bytes) -> tuple[str, int]:
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(blob), strict=False)
    if not 1 <= len(reader.pages) <= MAX_PAGES:
        raise ValueError("Brak stron lub zbyt duży dokument")
    parts = []
    size = 0
    for pg in reader.pages:
        text = pg.extract_text(extraction_mode="plain") or ""
        size += len(text)
        if size > MAX_TEXT:
            raise ValueError("Zbyt duża ilość tekstu")
        parts.append(text)
    return "\n\n".join(parts), len(reader.pages)


def _verified_identity(text: str, *, source: str, identity: str) -> bool:
    if len(text.strip()) < 1000:
        return False
    normalized = re.sub(r"\s+", "", text).casefold()
    if source == "sn":
        return re.sub(r"\W+", "", identity).casefold() in re.sub(r"\W+", "", text).casefold()
    if source == "eurlex":
        m = re.fullmatch(r"3(\d{4})([RLD])(\d{4})", identity)
        if not m:
            return False  # Nie oznaczamy wyroku TSUE jako rozporządzenia.
        year, typ, number = m.groups()
        expected = f"{year}/{int(number)}"
        first = normalized[:20000]
        typy = {"R": ("rozporządzenie",), "L": ("dyrektywa",),
                "D": ("decyzja",)}
        return expected in first and any(x in first for x in typy[typ])
    return False


def ingest_verified_pdf(url: str, *, source: str, identity: str,
                        directory: str) -> dict:
    """Pobierz, wyodrębnij tekst, sprawdź dokument, zapisz plik o nazwie SHA."""
    blob = _get_official_pdf(url, source)
    text, pages = _pdf_text(blob)
    if not _verified_identity(text, source=source, identity=identity):
        return {"status": "nieweryfikowalny_pdf",
                "uwaga": "PDF nie ma wystarczającego tekstu lub zawiera inną sygnaturę/numer aktu. "
                         "Nie dopisano go jako pełnego dokumentu.",
                "strony_pdf": pages}
    directory_path = Path(directory)
    directory_path.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    target = directory_path / (digest + ".txt")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory_path,
                                     prefix=".inprogress_", delete=False) as tmp:
        tmp.write(text)
        tmp_path = tmp.name
    os.replace(tmp_path, target)
    return {"status": "zweryfikowany_tekst_zapisany",
            "artifact_file": target.name,
            "artifact_sha256": digest,
            "liczba_znakow": len(text), "strony_pdf": pages,
            "adres_pdf": url, "dokument_pelny": True,
            "uwaga": "Wyodrębniono wszystkie strony udostępnionego PDF. "
                     "Aktualność i późniejsze nowelizacje oceniaj osobno."}
