"""Minimalny MCP: jedno narzędzie pobierania źródeł po identyfikatorach Repertorium.

Nie uruchamia i nie modyfikuje Repertorium. Nie udostępnia narzędzi wyszukiwania.
Dane prawnicze: źródła urzędowe, jawny status niekompletności, odpowiedzi po polsku.
"""
from __future__ import annotations

import asyncio
import json
import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .pool import POOL
from .registry import SOURCES
from .local_corpus import read_cache, read_eu_pl, read_ustawy, save_cache

PAGE_CHARS = 5000
MAX_HTML_BYTES = 4_000_000
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True,
                            destructiveHint=False, openWorldHint=True)
mcp = FastMCP(
    name="pobierz-dokument-prawny",
    instructions="Jeden endpoint do pobierania dokumentów po identyfikatorach "
                 "z Repertorium. Najpierw rozpoznaj dokładny numer Dz.U., CELEX, "
                 "SAOS lub NSA. Wyszukiwanie tematów wykonuje odrębne Repertorium. "
                 "Nie przedstawiaj snippetu ani samego linku jako pełnego dokumentu. "
                 "Wszystkie odpowiedzi po polsku, bez selektora języka.",
)


def rozpoznaj(identyfikator: str) -> tuple[str, str, str | None]:
    """(rodzaj, kanoniczny identyfikator, opcjonalny numer artykułu)."""
    raw = identyfikator.strip()
    m = re.fullmatch(r"(?:eli:)?(DU|MP)/(\d{4})/(\d{1,5})", raw, re.I)
    if m:
        return "eli", f"{m[1].upper()}/{m[2]}/{int(m[3])}", None
    m = re.fullmatch(
        r"(?:Dz\.?\s*U\.?|M\.?\s*P\.?)\s*(?:z\s*)?(\d{4})\s*(?:r\.?\s*)?"
        r"(?:poz\.?\s*)?(\d{1,5})", raw, re.I,
    )
    if m:
        pub = "MP" if raw.upper().lstrip().startswith("M") else "DU"
        return "eli", f"{pub}/{m[1]}/{int(m[2])}", None
    m = re.fullmatch(r"nsa:([A-Fa-f0-9]{10})", raw, re.I)
    if m:
        return "nsa", m[1].upper(), None
    m = re.fullmatch(r"saos:([1-9]\d{0,12})", raw, re.I)
    if m:
        return "saos", str(int(m[1])), None
    m = re.fullmatch(r"celex:([A-Z0-9/()\-]+)(?::pl)?", raw, re.I)
    if m:
        return "celex", m[1].upper(), None
    m = re.fullmatch(r"RODO(?:\s+art\.?\s*(\d+[a-z]?))?", raw, re.I)
    if m:
        return "celex", "32016R0679", m[1]
    m = re.fullmatch(r"ecli:(EU:[A-Z]+:\d{4}:\d+)", raw, re.I)
    if m:
        return "ecli", m[1].upper(), None
    m = re.fullmatch(r"eureka:(\d+)", raw, re.I)
    if m:
        return "eureka", m[1], None
    m = re.fullmatch(r"sn:([a-zA-Z0-9_\-]+)", raw, re.I)
    if m:
        return "sn", m[1], None
    m = re.fullmatch(r"edpb:([a-zA-Z0-9_\-]+)(?::pl)?", raw, re.I)
    if m:
        return "edpb", m[1], None
    m = re.fullmatch(r"ms:([A-Za-z0-9_\-]+)", raw, re.I)
    if m:
        return "ms", m[1], None
    return "nieznany", raw, None


def bezpieczny_adres(url: str | None, rodzaj: str) -> str | None:
    """Walidacja linku do wyświetlenia; URL nigdy nie jest pobierany jako adres sieciowy."""
    if not url or len(url) > 2000:
        return None
    try:
        u = urlparse(url)
        allowed = {
            "sn": {"www.sn.pl", "sn.pl"},
            "edpb": {"www.edpb.europa.eu", "edpb.europa.eu"},
            "ms": {"orzeczenia.ms.gov.pl"},
            "eureka": {"eureka.mf.gov.pl"},
        }.get(rodzaj, set())
        if u.scheme == "https" and not u.username and not u.password and u.hostname in allowed:
            return url
    except ValueError:
        pass
    return None


def stronicuj(tekst: str, strona: int) -> dict:
    start = (strona - 1) * PAGE_CHARS
    if start >= len(tekst) and tekst:
        return {"tekst": "", "dalszy_fragment": False, "kolejna_strona": None,
                "total_chars": len(tekst), "status": "poza_zakresem"}
    fragment = tekst[start:start + PAGE_CHARS]
    dalszy = start + len(fragment) < len(tekst)
    return {"tekst": fragment, "dalszy_fragment": dalszy,
            "kolejna_strona": strona + 1 if dalszy else None,
            "total_chars": len(tekst), "status": "znaleziony"}


class _TekstHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.part: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in ("p", "br", "div", "section", "h1", "h2", "h3", "li", "tr"):
            self.part.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        elif tag in ("p", "div", "section", "h1", "h2", "h3", "li", "tr"):
            self.part.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.part.append(data)

    def text(self) -> str:
        x = "".join(self.part)
        return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", x).strip()


def _odczyt_json(url: str) -> dict:
    with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=15) as res:
        raw = res.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("Metadane ELI przekraczają limit")
        return json.loads(raw)


def _odczyt_html(url: str) -> str:
    with urlopen(Request(url, headers={"Accept": "text/html"}), timeout=20) as res:
        raw = res.read(MAX_HTML_BYTES + 1)
        if len(raw) > MAX_HTML_BYTES:
            raise ValueError("Tekst aktu przekracza limit pobierania")
        ct = res.headers.get_content_charset() or "utf-8"
        html = raw.decode(ct, errors="replace")
    parser = _TekstHTML()
    parser.feed(html)
    return parser.text()


async def _eli(eli: str, strona: int, artykul: str | None = None) -> dict:
    pub, year, pos = eli.split("/")
    base = f"https://api.sejm.gov.pl/eli/acts/{pub}/{year}/{pos}"
    # PIERWSZEŃSTWO 1: USTAWY, lokalny SQLite z artykułami i ELI.
    try:
        local = await asyncio.to_thread(read_ustawy, eli, artykul)
    except Exception as exc:
        local = None  # awaria indeksu nie blokuje oddzielnego, zweryfikowanego cache
    if local:
        part = stronicuj(local["tekst"], strona)
        return {k: v for k, v in local.items() if k != "tekst"} | part | {
            "dokument_pelny": False, "pochodzenie": "lokalny_ustawy",
            "uwaga": local["uwaga"] + " Stan prawny sprawdź względem daty aktu.",
        }

    # PIERWSZEŃSTWO 2: cache urzędowych, już raz pobranych aktów.
    try:
        cached = await asyncio.to_thread(read_cache, "eli:" + eli)
    except Exception:
        cached = None
    if cached and cached["kompletny"]:
        part = stronicuj(cached["tekst"], strona)
        return {"identyfikator": "eli:" + eli, "typ": "akt_prawny",
                "zrodlo": cached["metadane"].get("źródło"),
                "adres_urzedowy": cached["adres_zrodlowy"],
                "pobrano_at": cached["pobrano_at"], "sha256": cached["sha256"],
                "pochodzenie": "lokalny_cache", "strona": strona,
                "dokument_pelny": True} | part

    # WYŁĄCZNIE FALLBACK: oficjalne ELI API.
    try:
        meta = await asyncio.to_thread(_odczyt_json, base)
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        return {"status": "błąd_źródła", "identyfikator": "eli:" + eli,
                "adres_urzedowy": base, "tekst": "", "dokument_pelny": False,
                "uwaga": f"Nie udało się pobrać metadanych ELI: {type(exc).__name__}"}
    result = {
        "identyfikator": f"eli:{eli}",
        "typ": "akt_prawny",
        "zrodlo": "API ELI Kancelarii Sejmu",
        "adres_urzedowy": base,
        "tytul": meta.get("title"),
        "data_ogloszenia": meta.get("promulgation"),
        "stan_prawny_na": meta.get("legalStatusDate"),
        "status_aktu": meta.get("status"),
        "zmiany_po_tekście": (meta.get("references") or {}).get("Nowelizacje po tekście jednolitym", []),
        "strona": strona,
        "uwaga": "Publikowany tekst nie musi odzwierciedlać wszystkich późniejszych nowelizacji.",
    }
    if not meta.get("textHTML"):
        return result | {
            "status": "tylko_link",
            "adres_pdf": base + "/text.pdf",
            "tekst": "",
            "dokument_pelny": False,
            "uwaga": "API nie udostępnia HTML tego aktu — wymagany odczyt urzędowego PDF.",
        }
    try:
        text = await asyncio.to_thread(_odczyt_html, base + "/text.html")
    except (HTTPError, URLError, TimeoutError, ValueError, LookupError) as exc:
        return result | {"status": "niedostępny_tekst", "tekst": "",
                         "dokument_pelny": False, "uwaga": f"Nie udało się odczytać HTML: {type(exc).__name__}"}
    try:
        saved = await asyncio.to_thread(
            save_cache, "eli:" + eli, jezyk="pl", tekst=text,
            url=base + "/text.html",
            metadane={"źródło": "API ELI Kancelarii Sejmu",
                      "eli": eli, "tytul": meta.get("title"),
                      "stan_prawny_na": meta.get("legalStatusDate"),
                      "rodzaj": "HTML bez załączników binarnych"},
        )
    except (OSError, ValueError) as exc:
        saved = False
    fragment = stronicuj(text, strona)
    return result | fragment | {
        "pochodzenie": "zdalny_fallback",
        "zapisano_lokalnie": saved,
        "sha256": __import__("hashlib").sha256(text.encode("utf-8")).hexdigest(),
        "format_tekstu": "tekst wyodrębniony z urzędowego HTML (układ może się różnić)",
        "adres_html": base + "/text.html",
        "dokument_pelny": not fragment["dalszy_fragment"] and strona == 1,
    }


async def _orzeczenie(kind: str, value: str, strona: int) -> dict:
    src = SOURCES.get(kind)
    base = ("https://www.saos.org.pl/judgments/" + value if kind == "saos"
            else "https://orzeczenia.nsa.gov.pl/doc/" + value)
    if src is None:
        return {"status": "niepodłączone_źródło", "identyfikator": kind + ":" + value,
                "adres_urzedowy": base, "tekst": "", "dokument_pelny": False}
    args = {"id": int(value)} if kind == "saos" else {"doc_id": value}
    args |= {"offset": (strona - 1) * PAGE_CHARS, "limit": PAGE_CHARS}
    try:
        response = await POOL.call_with_metadata(src, "get_judgment", args)
    except Exception as exc:
        return {"status": "błąd_źródła", "identyfikator": kind + ":" + value,
                "adres_urzedowy": base, "tekst": "", "dokument_pelny": False,
                "uwaga": f"Nie udało się pobrać orzeczenia: {type(exc).__name__}"}
    metadata = response.get("structured") or {}
    total = metadata.get("totalLength")
    has_more = metadata.get("hasMore")
    verified = type(total) is int and type(has_more) is bool
    is_error = response.get("is_error", False)
    return {
        "status": "błąd_źródła" if is_error else ("znaleziony" if verified else "niezweryfikowana_kompletność"),
        "identyfikator": kind + ":" + value,
        "typ": "orzeczenie",
        "zrodlo": "SAOS" if kind == "saos" else "CBOSA",
        "adres_urzedowy": base,
        "tekst": response.get("text", ""),
        "strona": strona,
        "dalszy_fragment": has_more if verified else None,
        "kolejna_strona": (strona + 1 if has_more else None) if verified else None,
        "total_chars": total if verified else None,
        "next_offset": metadata.get("nextOffset") if verified else None,
        "citations": metadata.get("citations", []),
        "dokument_pelny": verified and strona == 1 and not has_more and not is_error,
        "uwaga": None if verified else "Brak metadanych długości: tekst może być tylko pierwszym fragmentem orzeczenia.",
    }


async def pobierz_dokument(
    identyfikator: str, artykul: str | None = None,
    strona: int = 1, adres_zrodlowy: str | None = None,
) -> dict:
    """Pobierz dokument po ID z REPERTORIUM: eli:DU/2024/917, saos:166511,
    nsa:389F2C5B67, celex:32016R0679:pl, RODO art. 33.
    `strona` od 1. Brak dostępu do pełnego tekstu oznacz jawnie; nie zgaduj.
    Inne typy ID otrzymują zweryfikowany link lub informację o ograniczeniu.
    Nie używaj do wyszukiwania tematów; do tego służy REPERTORIUM.
    """
    if not isinstance(identyfikator, str) or not identyfikator.strip() or len(identyfikator) > 300:
        return {"status": "błędny_id", "uwaga": "Podaj identyfikator o długości do 300 znaków."}
    if type(strona) is not int or strona < 1 or strona > 10000:
        return {"status": "błędna_strona", "uwaga": "Strona musi być liczbą całkowitą od 1 do 10000."}
    kind, key, parsed_art = rozpoznaj(identyfikator)
    article = artykul or parsed_art
    if kind == "eli":
        wynik = await _eli(key, strona, article)
        if article and wynik.get("pochodzenie") != "lokalny_ustawy":
            wynik["uwaga_dot_artykulu"] = "Wersja zdalna/cache stronicuje cały akt; nie wyodrębnia art. " + str(article) + "."
        return wynik
    if kind in ("nsa", "saos"):
        return await _orzeczenie(kind, key, strona)

    if kind == "celex":
        uri = "https://eur-lex.europa.eu/legal-content/PL/TXT/?uri=CELEX:" + key
        # Wymagany urzędowy polski korpus — istniejący EN nie może go zastąpić.
        local = await asyncio.to_thread(read_eu_pl, key, article)
        if local:
            part = stronicuj(local["tekst"], strona)
            return {"status": "znaleziony", "identyfikator": "celex:" + key + ":pl",
                    "typ": "akt_UE", "pochodzenie": "lokalny_eu_pl",
                    "adres_urzedowy": local["adres_zrodlowy"],
                    "data_pobrania": local["pobrano_at"], "sha256": local["sha256"],
                    "dokument_pelny": True, "artykul": article} | part
        cached = await asyncio.to_thread(read_cache, "celex:" + key + ":pl")
        if cached and cached["kompletny"] and cached["metadane"].get("wersja_urzedowa_pl") is True:
            part = stronicuj(cached["tekst"], strona)
            return {"status": "znaleziony", "identyfikator": "celex:" + key + ":pl",
                    "typ": "akt_UE", "pochodzenie": "lokalny_cache",
                    "adres_urzedowy": cached["adres_zrodlowy"],
                    "data_pobrania": cached["pobrano_at"], "sha256": cached["sha256"],
                    "dokument_pelny": True, "artykul": article} | part
        return {"status": "tylko_link", "identyfikator": "celex:" + key + ":pl",
                "typ": "akt_UE", "adres_urzedowy": uri, "artykul": article,
                "dokument_pelny": False, "tekst": "",
                "uwaga": "Oficjalny pełny tekst PL nie został pobrany. Nie podstawiaj angielskiego snapshotu."}
    if kind == "ecli":
        return {"status": "tylko_link", "identyfikator": "ecli:" + key,
                "adres_urzedowy": "https://eur-lex.europa.eu/legal-content/PL/TXT/?uri=ECLI:" + key,
                "dokument_pelny": False, "tekst": ""}
    if kind in ("sn", "ms", "eureka", "edpb"):
        official = {
            "sn": "https://www.sn.pl/pl/wyszukiwarka-orzeczen",
            "eureka": "https://eureka.mf.gov.pl/informacje/podglad/" + key,
            "ms": "https://orzeczenia.ms.gov.pl/content/$N/" + key,
            "edpb": "https://www.edpb.europa.eu/",
        }[kind]
        url = bezpieczny_adres(adres_zrodlowy, kind) or official
        return {"status": "tylko_link", "identyfikator": kind + ":" + key,
                "adres_urzedowy": url, "dokument_pelny": False, "tekst": "",
                "uwaga": "ID pochodzi z indeksu Repertorium; bez oficjalnego pobrania pełnej treści nie potwierdzono tekstu."}
    return {"status": "nieobsługiwany_id", "identyfikator": identyfikator,
            "uwaga": "Nie rozpoznano jednoznacznego identyfikatora. Odszukaj document_id przez Repertorium."}


mcp.tool(pobierz_dokument, annotations=READ_ONLY)


def main() -> None:
    try:
        mcp.run()
    finally:
        asyncio.run(POOL.close_all())
