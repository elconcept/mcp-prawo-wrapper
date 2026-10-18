"""Source-agnostic, semantic-first case-law orchestration.

The caller supplies adapters for the already-running MCP servers. No secondary
SAOS downloader and no MS bulk scraper live here. The SAOS adapter owns both
its versioned mirror and its official-API fallback; MS owns a *separate*
discovery cache. Only verified source results are evidence, semantic hits
are navigation hints.
"""
from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal

Status = Literal["ok", "empty", "upstream_error"]
CourtKind = Literal["auto", "common", "administrative"]
Backend = Literal["repertorium", "saos", "nsa", "ms_cache", "ms_live"]


@dataclass(frozen=True)
class CaseHit:
    source: str
    source_id: str
    url: str | None = None
    case_number: str | None = None
    court: str | None = None
    judgment_date: str | None = None
    document_type: str | None = None
    snippet: str | None = None
    full_text_available: bool = False


@dataclass
class SearchBatch:
    status: Status
    hits: list[CaseHit] = field(default_factory=list)
    note: str | None = None


@dataclass
class CaseLawResult:
    status: Literal["found", "not_found_in_checked_sources", "partial"]
    records: list[dict]
    semantic_hints: list[CaseHit]
    checked: dict[str, Status]
    warnings: list[str]


SearchAdapter = Callable[[str, str | None], Awaitable[SearchBatch]]
# The Repertorium adapter returns hints, never authoritative source records.


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().casefold()


def _key(hit: CaseHit) -> tuple:
    # Strong, document-level identity is required. A shared sygnatura without
    # court/date/type is NOT enough (one case has judgment and justification).
    if all((hit.case_number, hit.court, hit.judgment_date, hit.document_type)):
        return (
            "document",
            _normalize(hit.court or ""),
            _normalize(hit.case_number or ""),
            hit.judgment_date,
            _normalize(hit.document_type or ""),
        )
    return ("source", hit.source, hit.source_id)


def combine_hits(hits: list[CaseHit]) -> list[dict]:
    grouped: dict[tuple, dict] = {}
    for hit in hits:
        key = _key(hit)
        if key not in grouped:
            grouped[key] = {
                "ref": f"{hit.source}:{hit.source_id}",
                "case_number": hit.case_number,
                "court": hit.court,
                "judgment_date": hit.judgment_date,
                "document_type": hit.document_type,
                "snippet": hit.snippet,
                "full_text_available": hit.full_text_available,
                "sources": [],
            }
        record = grouped[key]
        record["full_text_available"] |= hit.full_text_available
        record["sources"].append({
            "provider": hit.source,
            "id": hit.source_id,
            "url": hit.url,
        })
    return list(grouped.values())


async def find_case_law(
    query: str,
    adapters: dict[str, SearchAdapter],
    *,
    case_number: str | None = None,
    court_kind: CourtKind = "auto",
    semantic_timeout_s: float = 4.0,
    deep: bool = False,
) -> CaseLawResult:
    """Discover semantic leads first, then seek real source records.

    The source order is SAOS (which internally does dump->official API), NSA,
    the separate MS discovery index, then live MS portal as a *last resort*.
    Common-court-only and administrative-only searches skip irrelevant sources.
    On mixed topics, NSA and the MS discovery cache are still searched after
    SAOS hits; do not mistake an incomplete corpus for exhaustive coverage.
    """
    if not query.strip():
        raise ValueError("query must be non-empty")
    if court_kind not in ("auto", "common", "administrative"):
        raise ValueError("court_kind must be auto/common/administrative")

    checked: dict[str, Status] = {}
    warnings: list[str] = []
    semantic_hints: list[CaseHit] = []
    evidence: list[CaseHit] = []

    if semantic := adapters.get("repertorium"):
        try:
            s = await asyncio.wait_for(
                semantic(query, case_number), timeout=semantic_timeout_s
            )
            checked["repertorium"] = s.status
            semantic_hints = s.hits if s.status == "ok" else []
            if s.status == "upstream_error":
                warnings.append(s.note or "Repertorium unavailable; source search continued.")
        except (Exception, asyncio.TimeoutError) as exc:
            checked["repertorium"] = "upstream_error"
            warnings.append("Repertorium failed or timed out; source search continued.")

    if court_kind == "administrative":
        plan = ["nsa"]
    elif court_kind == "common":
        plan = ["saos", "ms_cache"]
    else:
        plan = ["saos", "nsa", "ms_cache"]

    for name in plan:
        adapter = adapters.get(name)
        if adapter is None:
            checked[name] = "upstream_error"
            warnings.append(f"{name} adapter not configured")
            continue
        try:
            batch = await adapter(query, case_number)
            checked[name] = batch.status
            if batch.status == "ok":
                evidence.extend(batch.hits)
            elif batch.status == "upstream_error":
                warnings.append(batch.note or f"{name} source failed")
        except Exception as exc:
            checked[name] = "upstream_error"
            warnings.append(f"{name} source failed: {type(exc).__name__}")

    # Avoid scraping the MS portal if authoritative sources already found
    # records, unless the caller explicitly requested a deeper search.
    if court_kind != "administrative" and (deep or not evidence):
        live = adapters.get("ms_live")
        if live is not None:
            try:
                batch = await live(query, case_number)
                checked["ms_live"] = batch.status
                if batch.status == "ok":
                    evidence.extend(batch.hits)
                elif batch.status == "upstream_error":
                    warnings.append(batch.note or "MS live portal unavailable")
            except Exception as exc:
                checked["ms_live"] = "upstream_error"
                warnings.append(f"MS live portal failed: {type(exc).__name__}")
        else:
            checked["ms_live"] = "upstream_error"
            warnings.append("MS live adapter not configured")

    failures = any(
        status == "upstream_error" for name, status in checked.items()
        if name != "repertorium"
    )
    if failures:
        status = "partial"
    elif evidence:
        status = "found"
    else:
        # This is deliberately NOT a claim that a judgment doesn't exist.
        status = "not_found_in_checked_sources"
    return CaseLawResult(
        status=status,
        records=combine_hits(evidence),
        semantic_hints=semantic_hints,
        checked=checked,
        warnings=warnings,
    )
