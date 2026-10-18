"""Parse semantic Repertorium responses without guessing document identifiers.

Repertorium is an aggregate over primary legal sources. Its document_id
prefix is the routing key, irrespective of the displayed URL (some SAOS hits
link to the MS portal, which is *not* the SAOS API identifier).
"""
from __future__ import annotations

import re
from typing import Any

_REF_TO_SOURCE = {
    "saos": "saos",
    "nsa": "nsa",
    "cbosa": "nsa",
    "eli": "isap",
    "eureka": "eureka",
    "uodo": "uodo",
    "krs": "krs",
    "ms": "ms",
}


def source_for_ref(ref: str) -> tuple[str, str] | None:
    if not isinstance(ref, str) or ":" not in ref:
        return None
    prefix, ident = ref.split(":", 1)
    if not ident.strip() or not re.fullmatch(r"[a-z0-9_-]+", prefix):
        return None
    source = _REF_TO_SOURCE.get(prefix)
    return (source, ident.strip()) if source else None


def parse_repertorium(text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise TypeError("Repertorium response must be text")
    total = re.search(r"(?m)^Znaleziono:\s*(\d+)\s*$", text)
    coverage = re.search(r"(?m)^Uwaga - pokrycie:\s*(.+)\s*$", text)
    blocks = re.split(r"(?m)(?=^- \*\*)", text)
    records: list[dict[str, Any]] = []
    for block in blocks:
        title_line = re.match(r"^- \*\*(.*?)\*\*\s+\(([^)\n]+)\)", block)
        if not title_line:
            continue

        def field(name: str) -> str | None:
            match = re.search(r"(?m)^  " + re.escape(name) + r":\s*(.*)$", block)
            return match.group(1).strip() if match else None

        ref = field("document_id")
        if not ref:
            continue
        snippet = re.search(r'(?ms)^  fragment: "(.*?)"(?=\n  (?:link|zrodlo):|\s*\Z)', block)
        link = field("link")
        if not link and ref.startswith("saos:"):
            ident = ref.split(":", 1)[1]
            if ident.isdigit():
                link = "https://www.saos.org.pl/judgments/" + ident
        if not link and ref.startswith("eli:"):
            link = "https://api.sejm.gov.pl/eli/acts/" + ref.split(":", 1)[1]
        routing = source_for_ref(ref)
        records.append({
            "document_ref": ref,
            "title": title_line.group(1),
            "date": title_line.group(2),
            "court_or_institution": field("sad"),
            "fragment": snippet.group(1).strip() if snippet else None,
            "source_url": link,
            "backend": routing[0] if routing else None,
            "direct_fetch_available": routing is not None,
        })
    return {
        "source": "repertorium",
        "discovery": "semantic",
        "total_reported": int(total.group(1)) if total else None,
        "coverage_note": coverage.group(1) if coverage else None,
        "results": records,
        "next": "Use pl_get_by_ref(document_ref) to read full text when available; "
                "for sources with no backend, follow source_url.",
    }
