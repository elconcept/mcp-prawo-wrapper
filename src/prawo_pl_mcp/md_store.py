"""Bounded Markdown source store inside the legal repository, no database or embeddings."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from .pagination import paginate

ROOT = Path(os.environ.get("PRAWO_MD_DIR", "/legal_sources"))
REL_ROOT = "opracowania/zrodla_prawne_mcp"
MAX_BYTES = 12_000_000


def slug(value: str, limit: int = 64) -> str:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", folded.lower()).strip("-")
    return (cleaned or "dokument")[:limit].strip("-") or "dokument"


def _folder(source: str) -> str:
    return slug(source or "unresolved", 30)


def _name(hit: dict, source: str, article: str = "") -> Path:
    identifier = str(hit.get("document_id") or "")
    title = str(hit.get("tytul") or hit.get("title") or "dokument")
    version = str(hit.get("as_of_date") or hit.get("na_dzien") or
                  hit.get("version") or hit.get("data") or "")
    stable = "\0".join((source, identifier or title, article, version))
    digest = hashlib.sha256(stable.encode()).hexdigest()[:12]
    directory = ROOT / _folder(source)
    if directory.is_symlink():
        raise ValueError("Symlink source directory forbidden")
    existing = sorted(directory.glob("*__" + digest + ".md")) if directory.is_dir() else []
    if existing:
        return existing[0]
    return directory / (slug(identifier.removeprefix(source + ":") or title, 58)
                        + "__" + slug(title, 45) + "__" + digest + ".md")


def _frontmatter(meta: dict) -> str:
    # JSON scalars/inline objects are valid YAML 1.2. Values never become YAML directives.
    return "---\n" + "".join(
        f"{key}: {json.dumps(value, ensure_ascii=False, default=str)}\n"
        for key, value in meta.items()
    ) + "---\n\n"


def _write(hit: dict, source: str, body: str, status: str,
           source_mcp: str | None, source_tool: str | None,
           article: str = "", warning: str | None = None) -> str:
    if not ROOT.is_dir():
        raise OSError("Markdown root is not mounted: " + str(ROOT))
    if len(body.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Document exceeds permitted size")
    target = _name(hit, source, article)
    base = ROOT.resolve(strict=True)
    if target.parent.is_symlink():
        raise ValueError("Symlink directory forbidden")
    if not target.parent.resolve(strict=False).is_relative_to(base):
        raise ValueError("Document path escapes Markdown root")
    target.parent.mkdir(mode=0o2770, parents=True, exist_ok=True)
    if target.parent.is_symlink() or not target.parent.resolve(strict=True).is_relative_to(base):
        raise ValueError("Unsafe source directory")
    target.parent.chmod(0o2770)
    if target.is_symlink():
        raise ValueError("Symlink document forbidden")
    if target.is_file() and status == "fragment_only":
        existing = target.read_text(encoding="utf-8")
        if ('content_status: "full"' in existing[:2000] or
                'content_status: "article_only"' in existing[:2000]):
            raise ValueError("Refusing to overwrite an existing resolved document with a fragment")
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    meta = {
        "schema_version": 1,
        "source": source,
        "original_repertorium_id": hit.get("document_id"),
        "canonical_document_id": hit.get("document_id"),
        "title": hit.get("tytul") or hit.get("title"),
        "document_date": hit.get("data"),
        "source_url": hit.get("zrodlo_url") or hit.get("source_url"),
        "source_mcp": source_mcp,
        "source_tool": source_tool,
        "article_selector": article or None,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "content_status": status,
        "as_of_date": hit.get("as_of_date") or hit.get("na_dzien"),
        "version": hit.get("version"),
        "full_text_unavailable": status == "fragment_only",
        "disclosure_required": status == "fragment_only",
        "warning": warning,
        "failure_reason": warning if status == "fragment_only" else None,
        "content_sha256": sha,
    }
    content = _frontmatter(meta) + body
    import tempfile
    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix=".tmp-", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporary, 0o660)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return REL_ROOT + "/" + target.relative_to(ROOT).as_posix()


async def write(hit: dict, source: str, body: str, status: str,
                source_mcp: str | None = None, source_tool: str | None = None,
                article: str = "", warning: str | None = None) -> str:
    return await asyncio.to_thread(_write, hit, source, body, status, source_mcp,
                                   source_tool, article, warning)


def _read(document_id: str, page: int, expected_sha256: str | None = None) -> dict:
    if not isinstance(document_id, str):
        raise ValueError("Document path must be a string")
    relative = document_id.removeprefix(REL_ROOT + "/")
    if relative.startswith("/") or "\\" in relative:
        raise ValueError("Absolute or backslash paths forbidden")
    parts = Path(relative).parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError("Path traversal forbidden")
    base = ROOT.resolve(strict=True)
    target = base.joinpath(*parts)
    # Validate all components, preventing symlink escapes, even within the allowed tree.
    for i in range(1, len(parts) + 1):
        if base.joinpath(*parts[:i]).is_symlink():
            raise ValueError("Symlink-based file access forbidden")
    resolved = target.resolve(strict=True)
    if not resolved.is_relative_to(base) or resolved.suffix != ".md" or not resolved.is_file():
        raise ValueError("Path is outside the Markdown source directory")
    if resolved.stat().st_size > MAX_BYTES:
        raise ValueError("Document exceeds permitted size")
    full = resolved.read_text(encoding="utf-8")
    meta = {}
    body = full
    if full.startswith("---\n"):
        sep = full.find("\n---\n", 4)
        if sep >= 0:
            for line in full[4:sep].splitlines():
                key, colon, val = line.partition(": ")
                if colon and re.fullmatch(r"[a-z][a-z0-9_]*", key):
                    try:
                        meta[key] = json.loads(val)
                    except ValueError:
                        continue
            body = full[sep + 5:].lstrip("\n")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if meta.get("content_sha256") and meta["content_sha256"] != digest:
        raise ValueError("Stored Markdown content integrity check failed")
    if expected_sha256 and expected_sha256 != digest:
        raise ValueError("Markdown changed between page calls; restart reading at page 1")
    out = paginate(body, page)
    out.update({
        "page": out["page_number"], "source": "md", "document_id": document_id,
        "content_status": meta.get("content_status", "unknown"),
        "source_url": meta.get("source_url"), "origin_source": meta.get("source"),
        "content_sha256": meta.get("content_sha256"),
        "pagination": "aggregator",
    })
    if out["has_more"]:
        out["next_call"] = {
            "tool": "pl_get_document",
            "arguments": {"source": "md", "document_id": document_id,
                          "page": out["page"] + 1,
                          "extra": {"expected_sha256": digest}}
        }
    if out["content_status"] == "fragment_only":
        out["user_disclosure_required"] = True
        out["warning"] = (meta.get("warning")
                          or "Nie udało się uzyskać pełnej treści dokumentu. "
                             "Przedstawiono wyłącznie fragment z Repertorium.")
    return out


async def read(document_id: str, page: int,
               expected_sha256: str | None = None) -> dict:
    return await asyncio.to_thread(_read, document_id, page, expected_sha256)
