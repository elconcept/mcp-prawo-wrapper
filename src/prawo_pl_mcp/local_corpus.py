"""Lokalne dokumenty prawne: USTAWY SQLite i trwały cache resolvera.

Nie zapisuje do istniejących baz USTAWY/SAOS/UE. Każde źródło zachowuje
własną bazę, a dokument pobrany tylko w fallback trafia do osobnej bazy
resolvera, po sprawdzeniu tożsamości i kompletności.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any

CACHE_DB_ENV = "PRAWO_RESOLVER_CACHE"
USTAWY_DB_ENV = "PRAWO_USTAWY_SQLITE"
EU_PL_DB_ENV = "PRAWO_EU_PL_SQLITE"
DEFAULT_CACHE = "/data/prawo-resolver.sqlite"
_WRITE_LOCK = threading.Lock()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connection(path: str, *, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        uri = Path(path).resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10)
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS documents (
        identyfikator TEXT NOT NULL,
        jezyk TEXT NOT NULL,
        tekst TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        adres_zrodlowy TEXT NOT NULL,
        pobrano_at TEXT NOT NULL,
        kompletny INTEGER NOT NULL CHECK(kompletny IN (0,1)),
        metadane_json TEXT NOT NULL,
        PRIMARY KEY(identyfikator, jezyk)
      );
      CREATE INDEX IF NOT EXISTS idx_documents_fetched ON documents(pobrano_at);
    """)


def read_cache(identyfikator: str, *, jezyk: str = "pl",
               path: str | None = None, existing_only: bool = False) -> dict | None:
    file = path or os.environ.get(CACHE_DB_ENV, DEFAULT_CACHE)
    if not Path(file).is_file():
        return None
    with _connection(file, read_only=True) as conn:
        try:
            row = conn.execute(
                "SELECT * FROM documents WHERE identyfikator=? AND jezyk=?",
                (identyfikator, jezyk),
            ).fetchone()
        except sqlite3.OperationalError:
            if existing_only:
                return None
            raise
    if row is None:
        return None
    d = dict(row)
    # Nie ufaj zapisowi jeśli treść zmieniono poza protokołem zapisu.
    if hashlib.sha256(d["tekst"].encode("utf-8")).hexdigest() != d["sha256"]:
        return None
    d["kompletny"] = bool(d["kompletny"])
    d["metadane"] = json.loads(d.pop("metadane_json"))
    return d


def save_cache(identyfikator: str, *, jezyk: str, tekst: str, url: str,
               metadane: dict[str, Any], kompletny: bool = True,
               path: str | None = None) -> bool:
    """Zapis tylko zweryfikowanej, kompletnej treści źródłowej.

    Paginację częściową zapisujemy dopiero po złożeniu WSZYSTKICH fragmentów;
    nie zapisujemy streszczeń, snippetów ani stron logowania/challenge.
    """
    if (not kompletny or len(tekst.strip()) < 100 or not url.startswith("https://")
            or jezyk != "pl" or not identyfikator or "źródło" not in metadane):
        return False
    if len(tekst.encode("utf-8")) > 25_000_000:
        return False
    file = path or os.environ.get(CACHE_DB_ENV, DEFAULT_CACHE)
    digest = hashlib.sha256(tekst.encode("utf-8")).hexdigest()
    with _WRITE_LOCK:
        with _connection(file) as conn:
            _init(conn)
            conn.execute(
                """INSERT INTO documents
                   (identyfikator, jezyk, tekst, sha256, adres_zrodlowy,
                    pobrano_at, kompletny, metadane_json)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                   ON CONFLICT(identyfikator, jezyk) DO UPDATE SET
                    tekst=excluded.tekst, sha256=excluded.sha256,
                    adres_zrodlowy=excluded.adres_zrodlowy,
                    pobrano_at=excluded.pobrano_at, kompletny=excluded.kompletny,
                    metadane_json=excluded.metadane_json""",
                (identyfikator, jezyk, tekst, digest, url, _utc(),
                 json.dumps(metadane, ensure_ascii=False)),
            )
    return True


def read_ustawy(eli: str, artykul: str | None = None,
                path: str | None = None) -> dict | None:
    """Bezpośredni lokalny odczyt 37 aktów USTAWY, bez zapytań sieciowych.

    Baza mcp-ustawy jest tylko do odczytu. \`eli\` jest ściśle porównywany,
    więc inny tekst jednolity nie zostanie omyłkowo zwrócony jako żądana wersja.
    """
    file = path or os.environ.get(USTAWY_DB_ENV)
    if not file or not Path(file).is_file():
        return None
    with _connection(file, read_only=True) as conn:
        akt = conn.execute(
            "SELECT * FROM akty WHERE UPPER(eli)=UPPER(?)", (eli,)
        ).fetchone()
        if akt is None:
            return None
        cols = dict(akt)
        if artykul:
            normalized = artykul.strip().lower().replace("art.", "").strip()
            row = conn.execute(
                "SELECT art, jednostka, brzmienie FROM artykuly "
                "WHERE akt=? AND art=?", (cols["akt"], normalized)
            ).fetchone()
            if row is None:
                return None
            rows = [row]
        else:
            rows = conn.execute(
                "SELECT art, jednostka, brzmienie FROM artykuly "
                "WHERE akt=? ORDER BY rowid", (cols["akt"],)
            ).fetchall()
    if not rows:
        return None
    body = "\n\n".join(str(row["brzmienie"] or "").strip() for row in rows
                     if (row["brzmienie"] or "").strip())
    if not body:
        return None
    return {
        "tekst": body, "identyfikator": "eli:" + eli,
        "tytul": cols.get("tytul"), "akt": cols["akt"],
        "stan_na": cols.get("stan_na"),
        "tekst_jednolity": cols.get("tekst_jednolity"),
        "zrodlo": cols.get("zrodlo") or "USTAWY",
        "adres_urzedowy": f"https://api.sejm.gov.pl/eli/acts/{eli}",
        "tryb": "ustawy_sqlite",
        "artykul": artykul,
        # Baza USTAWY przechowuje artykuły, a nie pełne załączniki,
        # preambułę, pieczęcie, tabele i rysunki z urzędowej publikacji.
        "dokument_pelny": False,
        "uwaga": "Tekst artykułów z lokalnej bazy USTAWY. Nie jest to pełna "
                 "rekonstrukcja urzędowego Dz.U. (np. załączników).",
    }


def read_eu_pl(celex: str, artykul: str | None = None) -> dict | None:
    """Odczytaj wyłącznie urzędowy polski korpus, nie angielski EU-COMPLIANCE."""
    file = os.environ.get(EU_PL_DB_ENV)
    if not file:
        return None
    key = f"celex:{celex}:pl"
    row = read_cache(key, path=file, existing_only=True)
    if row and row["kompletny"] and row["metadane"].get("wersja_urzedowa_pl") is True:
        return row | {"tryb": "eu_pl_sqlite"}
    return None
