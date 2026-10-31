"""Odizolowany adapter PDF-only ELI oparty na legal-cite-pl.

Wymaga:
- legal-cite-pl w dokładnym commicie 2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988
- eli2md@v0.6.70 (biblioteka autora, przypięta wersja)
- Poppler/pdftotext i httpx

NIE nadaje urzędowego statusu ekstraktowi. Oryginałem jest pobrany PDF.
Adapter korzysta bezpośrednio z kodu autora dotyczącego struktury i
wierności artykułu, ale NIE wykonuje jego sieciowego odczyt(ident).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from .pdf_ingest import _get_official_pdf


def _normalizuj_artykul(raw: str) -> str:
    normalized = re.sub(r"(?i)^art\.?\s*", "", raw.strip())
    normalized = normalized.replace("^", "_")
    if not re.fullmatch(r"\d{1,4}(?:_[0-9]{1,3}[a-z]?|[a-z]{1,3})?", normalized, re.I):
        raise ValueError("Nieprawidłowy numer artykułu")
    return normalized.lower()


def _zapisz_niezmienny(folder: Path, data: bytes, extension: str) -> tuple[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    file = folder / (digest + extension)
    if not file.exists():
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".tmp-",
                                         suffix=extension, delete=False) as temp:
            temp.write(data)
            tmp = Path(temp.name)
        # tempfile tworzy plik z mode 0600. Worker zapisuje jako root, a
        # odrębny resolver uruchomiony pod UID 1029 czyta wspólny
        # katalog wyłącznie read-only. Urzędowe akty i ich ekstrakty
        # mogą być odczytywane przez ten serwis bez prawa zapisu.
        # Nadaj mode przed atomowym rename (nie ma okna z nieczytelnym
        # docelowym artefaktem).
        tmp.chmod(0o644)
        tmp.replace(file)
    if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
        raise ValueError("Naruszona integralność artefaktu")
    return digest, file


def przeanalizuj_pdf_eli(
    eli: str, art: str, destination: str, *,
    pdf_data: bytes | None = None, na_dzien: str | None = None,
) -> dict:
    """Ścisły ELI + sprawdzona pojedyncza jednostka, nigdy cały akt w jednym statusie.

    Gdy nie ma niezależnej warstwy pdftotext albo nie przechodzi ona
    kontroli autora legal-cite, odpowiedź jest kandydatem, nie cytatem.
    """
    if not re.fullmatch(r"(?:DU|MP)/\d{4}/\d{1,5}", eli):
        return {"status": "błędny_id", "dokument_pelny": False}
    try:
        art_key = _normalizuj_artykul(art)
    except (ValueError, AttributeError):
        return {"status": "błędny_artykul", "dokument_pelny": False}
    if na_dzien is not None:
        return {"status": "brak_zweryfikowanego_brzmienia_na_dzien",
                "identyfikator": "eli:" + eli, "artykul": art_key,
                "dokument_pelny": False, "artykul_kompletny": False,
                "uwaga": "Data parsera nie oznacza historycznego stanu prawnego."}
    source_url = f"https://api.sejm.gov.pl/eli/acts/{eli}/text.pdf"
    if pdf_data is None:
        pdf_data = _get_official_pdf(source_url, "eli")
    if not pdf_data.startswith(b"%PDF-"):
        return {"status": "nieprawidłowy_pdf", "dokument_pelny": False}
    # Import jest odroczony. Moduł działa w odrębnym wewnętrznym workerze:
    # nie wymaga wstrzykiwania zależności legal-cite do FastMCP resolvera.
    from legal_cite import pdf_tj as lc

    root = Path(destination)
    pdf_sha, pdf = _zapisz_niezmienny(root, pdf_data, ".pdf")
    converter = lc.wersja_konwertera()
    stamp = hashlib.sha256(f"{pdf_sha}:{converter}:eli2md-v1".encode()).hexdigest()[:20]
    md_file = root / f"{pdf_sha}-{stamp}.md"
    text_file = root / f"{pdf_sha}-pdftotext.txt"
    # Ograniczenie współbieżności egzekwowane na poziomie wewnętrznego MCP.
    try:
        md = lc._konwertuj(pdf, md_file)
        raw = lc._warstwa(pdf, text_file)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as exc:
        return {"status": "błąd_konwersji", "identyfikator": "eli:" + eli,
                "adres_pdf": source_url, "pdf_sha256": pdf_sha,
                "dokument_pelny": False, "uwaga": type(exc).__name__}
    if not raw:
        return {"status": "wymaga_ocr", "identyfikator": "eli:" + eli,
                "adres_pdf": source_url, "pdf_sha256": pdf_sha,
                "dokument_pelny": False}
    try:
        footnotes = lc.przypisy_md(md)
        from datetime import date
        at_date = date.fromisoformat(na_dzien) if na_dzien else date.today()
        units, monotonic = lc.jednostki_md(md, footnotes, dzis=at_date)
        token_list = lc._tokeny_pdftotext(raw)
        excluded = lc.wyjasnienia_warstwy(token_list, footnotes, eli.split("/")[-1])
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        return {"status": "niejednoznaczna_struktura", "identyfikator": "eli:" + eli,
                "adres_pdf": source_url, "pdf_sha256": pdf_sha,
                "dokument_pelny": False, "uwaga": type(exc).__name__}

    found = [unit for unit in units if unit.klucz == art_key]
    report = {
        "silnik": "legal-cite-pl/pdf_tj.py",
        "wersja_legal_cite": "2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988",
        "wersja_eli2md": converter,
        "wersja_pdftotext": lc.wersja_pdftotext(),
        "liczba_jednostek": len(units),
        "monotoniczna_numeracja": bool(monotonic),
        "liczba_trafien_artykulu": len(found),
        "na_dzien": at_date.isoformat(),
        "ocena_aktualnosci": "niezweryfikowana",
    }
    if not monotonic or len(found) != 1 or found[0].niejednoznaczne:
        return {"status": "niejednoznaczna_struktura",
                "identyfikator": "eli:" + eli, "artykul": art_key,
                "adres_pdf": source_url, "pdf_sha256": pdf_sha,
                "raport": report, "dokument_pelny": False}
    article = found[0]
    checked = lc.wiernosc_pdftotext(article, token_list, excluded)
    report["wierny_odczyt"] = bool(checked.ok)
    report["powod"] = checked.powod
    report["niewyjasnione_slowa"] = checked.niewyjasnione[:10]
    if not checked.ok or not article.czysty().strip():
        return {"status": "rozbieznosc_wiernosci", "identyfikator": "eli:" + eli,
                "artykul": art_key, "adres_pdf": source_url,
                "pdf_sha256": pdf_sha, "raport": report, "dokument_pelny": False}

    text = article.czysty()
    article_sha, text_path = _zapisz_niezmienny(root, text.encode("utf-8"), ".txt")
    report_sha, _ = _zapisz_niezmienny(
        root, json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8"), ".json"
    )
    return {
        "status": "wierny_odczyt_artykulu_z_pdf",
        "identyfikator": "eli:" + eli,
        "artykul": art_key,
        "artykul_kompletny": True,
        "dokument_pelny": False,  # NIE potwierdzono załączników i całego aktu
        "tekst_prawnie_nieurzedowy": True,
        "wersja_publikacji": eli,
        "adres_pdf": source_url,
        "pdf_sha256": pdf_sha,
        "artifact_pdf": pdf.name,
        "artifact_file": text_path.name,
        "artifact_sha256": article_sha,
        "raport_sha256": report_sha,
        "raport": report,
        "uwaga": "Wierny odczyt artykułu według dwuczytnikowej kontroli legal-cite; "
                 "wiążący jest oryginalny PDF, a aktualność na dzień wymaga oddzielnej analizy.",
    }
