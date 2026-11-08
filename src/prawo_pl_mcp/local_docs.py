"""Minimal on-demand document store for the personal MCP gateway.

No bulk SAOS import, no hashes or version history. PostgreSQL stores full text only
when a document was actually requested or pre-fetched from a search hit.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import zlib
from pathlib import Path

import psycopg
from bs4 import BeautifulSoup

SAOS_DUMP = "/saos/saos.sqlite"
KNOWN = {"saos", "nsa", "uodo", "kio", "isap"}


def route(source: str, document_id: str) -> tuple[str, str]:
    if source in ("auto", "repertorium"):
        prefix, sep, value = document_id.partition(":")
        if not sep:
            raise ValueError("Auto resolver requires source-prefixed ID: saos:..., nsa:..., kio:..., uodo:..., eli:...")
        source = "isap" if prefix == "eli" else prefix
        if source not in KNOWN:
            raise ValueError(f"No full-text resolver for source '{prefix}'")
        document_id = value
    elif source == "isap" and document_id.startswith("eli:"):
        document_id = document_id[4:]
    elif document_id.startswith(source + ":"):
        document_id = document_id[len(source) + 1:]
    return source, document_id


def cache_id(source: str, document_id: str) -> str:
    return ("eli" if source == "isap" else source) + ":" + document_id


def _database_password() -> str:
    return Path(os.getenv("PRAWO_DB_PASSWORD_FILE", "/run/secrets/db_password")).read_text().strip()


async def _connect() -> psycopg.AsyncConnection:
    return await psycopg.AsyncConnection.connect(
        host=os.getenv("PRAWO_DB_HOST", "prawo-vector-db"),
        dbname=os.getenv("PRAWO_DB_NAME", "prawo"),
        user=os.getenv("PRAWO_DB_USER", "prawo"),
        password=_database_password(),
        connect_timeout=4,
    )


async def read_cached(document_id: str) -> str | None:
    try:
        async with await _connect() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT full_text FROM legal_documents WHERE document_id=%s", (document_id,))
                row = await cursor.fetchone()
                return row[0] if row else None
    except (psycopg.Error, OSError):
        return None


async def save_cached(document_id: str, source: str, full_text: str) -> bool:
    if len(full_text.strip()) < 50 or looks_truncated(full_text):
        return False
    try:
        async with await _connect() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    """INSERT INTO legal_documents (document_id,source,full_text)
                       VALUES (%s,%s,%s)
                       ON CONFLICT (document_id) DO UPDATE
                       SET full_text=excluded.full_text, fetched_at=now()""",
                    (document_id, source, full_text),
                )
        return True
    except (psycopg.Error, OSError):
        return False


def looks_truncated(text: str) -> bool:
    return "Skrocono. Pelna tresc:" in text or "[...] Skrocono." in text


def _read_saos_sync(saos_id: str) -> str | None:
    if not saos_id.isdecimal() or not os.path.isfile(SAOS_DUMP):
        return None
    with sqlite3.connect("file:" + SAOS_DUMP + "?mode=ro", uri=True, timeout=5) as db:
        db.execute("PRAGMA query_only=ON")
        row = db.execute("SELECT data FROM judgments WHERE id=?", (int(saos_id),)).fetchone()
    if not row:
        return None
    raw = json.loads(zlib.decompress(row[0]))
    soup = BeautifulSoup(raw.get("textContent") or "", "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    return text if len(text) >= 50 else None


async def read_saos_dump(saos_id: str) -> str | None:
    try:
        return await asyncio.to_thread(_read_saos_sync, saos_id)
    except (sqlite3.Error, OSError, ValueError, zlib.error):
        return None


def uodo_signature(document_id: str) -> str | None:
    """Translate Repertorium's UODO URN to a public decision signature."""
    match = re.search(r"(\d{4})[:_]([a-z]{2,8})_(\d+)_(\d+)$", document_id, re.I)
    if match:
        year, dept, series, number = match.groups()
        return f"{dept.upper()}.{series}.{number}.{year}"
    if re.fullmatch(r"[A-Za-z]+\.\d+\.\d+\.\d{4}", document_id):
        return document_id
    return None


async def resolve_uodo_id(source, document_id: str, call) -> str:
    if document_id.startswith("PublicDocument-"):
        return document_id
    signature = uodo_signature(document_id)
    if not signature:
        return document_id
    reply = await call(source, "uodo_search_decisions", {"caseNumber": signature, "count": 5, "from": 0})
    match = re.search(r"(?m)^ID:\s*(PublicDocument-[^\s]+)", reply)
    return match.group(1) if match else document_id


def text_from_connector(raw: str, source: str) -> str:
    """Unwrap KIO's structured JSON, leaving other native full texts intact."""
    if source == "kio":
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and isinstance(obj.get("content_text"), str):
                return obj["content_text"]
        except ValueError:
            pass
    return raw



def _read_eli_pdf_sync(eli: str) -> str | None:
    """Extract a current official Polish act PDF on demand (no bulk ingestion)."""
    if not re.fullmatch(r"(DU|MP)/\d{4}/\d+", eli):
        return None
    import io
    import urllib.request

    from pypdf import PdfReader

    url = "https://api.sejm.gov.pl/eli/acts/" + eli + "/text.pdf"
    request = urllib.request.Request(url, headers={"User-Agent": "prawo-pl-mcp-personal/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read(25_000_001)
    if not payload.startswith(b"%PDF") or len(payload) > 25_000_000:
        return None
    reader = PdfReader(io.BytesIO(payload))
    text = "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
    return text if len(text) >= 500 else None


async def read_eli_pdf(eli: str) -> str | None:
    try:
        return await asyncio.to_thread(_read_eli_pdf_sync, eli)
    except (OSError, ValueError, RuntimeError):
        return None
