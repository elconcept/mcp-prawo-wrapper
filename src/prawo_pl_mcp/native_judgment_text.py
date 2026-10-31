"""Bezstratne wydzielanie natywnego fragmentu orzeczenia SAOS/NSA.

Metadata (returnedLength/offset) bez właściwego fragmentu nie są tekstem.
Nie wycinamy tekstu po nagłówkach na podstawie samej jego długości;
wymagana jest zgodna etykieta zakresu i tożsamość orzeczenia.
"""
from __future__ import annotations

import re
from typing import Any

# Format surowego tools/call SAOS 1.5.0 potwierdzony 2026-10-31.
# Wersje z poprawionym structuredContent.text nie wymagają tej ekstrakcji.
_RANGE_SAOS = re.compile(
    r"(?m)^--- Tresc \(znaki ([0-9]+)-([0-9]+) z ([0-9]+) lacznie\) ---\r?\n"
)
# PR NSA #2, formatJudgment: dokładny układ Unicode/odstępów.
_RANGE_NSA = re.compile(
    r"(?m)^--- Treść orzeczenia \(znaki ([0-9]+)–([0-9]+) z ([0-9]+)\) ---\r?\n"
)


def _valid_meta(meta: dict[str, Any], offset: int, limit: int) -> bool:
    total, returned, more, next_offset = (
        meta.get("totalLength"), meta.get("returnedLength"),
        meta.get("hasMore"), meta.get("nextOffset")
    )
    if (type(offset) is not int or type(limit) is not int
            or offset < 0 or limit < 1
            or type(total) is not int or type(returned) is not int
            or total < offset or returned != min(limit, total - offset)
            or meta.get("offset") != offset
            or type(more) is not bool
            or more != (offset + returned < total)
            or (next_offset != offset + returned if more
                else next_offset not in (None, offset + returned))):
        return False
    return True


def extract_native_judgment_text(
    kind: str, source_id: str, body: str, meta: dict[str, Any],
    *, offset: int, limit: int
) -> str | None:
    """Zwróć *samą* zawartość zakresu, w innym wypadku None.

    Preferowany czysty fragment z structuredContent.text. Starszy SAOS
    zwraca go w sformatowanym content.text, w otoczeniu metadanych i
    instrukcji paginacji. Nie można tego zapisać bez usunięcia ramki.
    """
    if kind not in ("saos", "nsa") or not isinstance(meta, dict):
        return None
    if not _valid_meta(meta, offset, limit):
        return None
    expected = meta["returnedLength"]
    direct = meta.get("text")
    if isinstance(direct, str) and len(direct) == expected:
        return direct
    if not isinstance(body, str):
        return None
    if len(body) == expected:
        return body

    match = (_RANGE_SAOS if kind == "saos" else _RANGE_NSA).search(body)
    if match is None:
        return None
    start, end, total = (int(v) for v in match.groups())
    if ((start, end, total) !=
            (offset, offset + expected, meta["totalLength"])):
        return None

    heading = body[:match.start()]
    if kind == "saos":
        if (not source_id.isdecimal() or
                not re.search(r"(?m)^ID SAOS\s*:\s*" + re.escape(source_id) +
                              r"\s*$", heading)):
            return None
        if not heading.startswith("=== ORZECZENIE SAOS ==="):
            return None
    else:
        if (not re.fullmatch(r"[0-9A-Fa-f]{10}", source_id) or
                not re.search(r"(?m)^ID CBOSA\s*:\s*" +
                              re.escape(source_id) + r"\s*$", heading, re.I)):
            return None
        if not heading.startswith("=== ORZECZENIE CBOSA"):
            return None

    from_pos = match.end()
    to_pos = from_pos + expected
    if len(body) < to_pos:
        return None
    text = body[from_pos:to_pos]
    suffix = body[to_pos:]
    if kind == "saos":
        if suffix:
            expected_suffix = (
                r"\r?\n\[\.\.\.\] Skrocono\. Nastepny fragment: "
                r"get_judgment\(id=" + re.escape(source_id) +
                r", offset=" + str(offset + expected) +
                r", limit=\d+\)\. Pelna tresc: https://www\.saos\.org\.pl/judgments/" +
                re.escape(source_id)
            )
            if re.fullmatch(expected_suffix, suffix) is None:
                return None
    else:
        # NSA #2 dodaje wyłącznie jedną stopkę na nieostatnim zakresie.
        # Nie przyjmuj jej po ostatnim fragmencie ani niespodziewanych danych.
        if meta["hasMore"]:
            expected_suffix = (
                r'\r?\nDalsza treść: get_judgment\(doc_id="' +
                re.escape(source_id) + r'", offset=' +
                str(offset + expected) + r', limit=\d+\)\.'
            )
            if re.fullmatch(expected_suffix, suffix) is None:
                return None
        elif suffix:
            return None
    return text
