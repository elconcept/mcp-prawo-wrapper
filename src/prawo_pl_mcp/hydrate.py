"""Repertorium hit hydration through existing MCP servers; preserves every original snippet."""
from __future__ import annotations

import asyncio
import json
import os
import re
import unicodedata
from collections.abc import Awaitable, Callable
from typing import Any

from . import md_store

Invoke = Callable[[str, str, dict], Awaitable[str]]
WARNING = (
    "Nie udało się uzyskać pełnej treści dokumentu. "
    "Przedstawiono wyłącznie fragment z Repertorium. "
    "Model ma obowiązek przekazać tę informację użytkownikowi."
)
_SIG = re.compile(
    r"\b([IVXLCM]{1,8}\s+[A-ZĄĆĘŁŃÓŚŹŻ]{1,9}\s+\d{1,6}/\d{2,4})\b", re.I,
)
_ART = re.compile(r"\bart\.?\s*(\d+[a-z]?)\b", re.I)
_PAR = re.compile(r"(?:^|\s)§\s*(\d+[a-z]?)\b", re.I)
MAX_DOC_CHARS = 3_000_000
PER_HIT_TIMEOUT = float(os.environ.get("PRAWO_HYDRATE_TIMEOUT", "250"))
CONCURRENCY = int(os.environ.get("PRAWO_HYDRATE_CONCURRENCY", "3"))


def _fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.lower())
    return re.sub(r"[^a-z0-9]", "", value.encode("ascii", "ignore").decode())


def _signature(value: str) -> str | None:
    match = _SIG.search(value)
    return " ".join(match.group(1).split()).upper() if match else None


def _decode(raw: str) -> tuple[str, dict]:
    """Keep an entire source document, not the search snippet."""
    if not isinstance(raw, str) or not raw.strip():
        raise LookupError("Source returned an empty response")
    stripped = raw.strip()
    if stripped.startswith(("❌", "[upstream_error]", "[source_unavailable]", "Błąd weryfikacji")):
        raise LookupError(stripped[:300])
    try:
        obj = json.loads(stripped)
    except ValueError:
        return raw, {}
    if not isinstance(obj, dict):
        return raw, {}
    if obj.get("isError") or obj.get("error") or obj.get("success") is False:
        raise LookupError(str(obj.get("error") or obj)[:260])
    if isinstance(obj.get("result"), dict):
        obj = obj["result"]
    if obj.get("truncated") is True or obj.get("has_more") is True or obj.get("hasMore") is True:
        raise LookupError("Source returned an incomplete/partial document")
    if obj.get("total_pages", 1) not in (None, 1) and "page" in obj:
        raise LookupError("Source paginated the text; all source pages must be collected")
    for key in ("content_text", "full_text", "fullText", "textContent", "text",
                "body", "content", "decisionText"):
        if isinstance(obj.get(key), str) and len(obj[key]) > 30:
            return obj[key], obj
    raise LookupError("Source returned metadata without confirmed document text")


def _valid(content: str) -> str:
    if len(content.strip()) < 45:
        raise LookupError("Source text too short to qualify as a resolved document")
    if len(content) > MAX_DOC_CHARS:
        raise LookupError("Document exceeds maximum size for text retrieval")
    if "Skrocono. Pelna tresc:" in content or "[...] Skrocono." in content:
        raise LookupError("Source explicitly returned truncated text")
    return content


def _article(hit: dict, query: str) -> str | None:
    # Prefer explicit leading article in the hit, otherwise the requested article.
    fragment = str(hit.get("fragment") or "")
    m = re.match(r"^\s*(art\.?\s*\d+[a-z]?|§\s*\d+[a-z]?)\b", fragment, re.I)
    if m:
        return " ".join(m.group(1).split())
    for pattern, prefix in ((_ART, "art."), (_PAR, "§")):
        m = pattern.search(query)
        if m:
            # Do not transfer an article from a named act to a semantically related,
            # different act just because it was in the result set.
            title = str(hit.get("tytul") or "")
            text = _fold(query)
            meaningful = re.findall(r"[a-zA-Ząćęłńóśźż]{5,}", title)
            matches = sum(_fold(w) in text for w in meaningful)
            if title and matches < 2:
                return None
            return f"{prefix} {m.group(1)}"
    return None


def _uodo_signature(raw: str) -> str | None:
    if re.fullmatch(r"[A-Za-z]+\.\d+\.\d+\.\d{4}", raw):
        return raw
    m = re.search(r"(\d{4})[:_]([a-z]{2,8})_(\d+)_(\d+)$", raw, re.I)
    if m:
        year, dept, series, number = m.groups()
        return f"{dept.upper()}.{series}.{number}.{year}"
    return None


_SAOS_PAGE_RE = re.compile(
    r"(?m)^--- Tresc \(znaki (\d+)-(\d+) z (\d+) lacznie\) ---\n"
)
_SAOS_NEXT_RE = re.compile(
    r"\n\[\.\.\.\] Skrocono\. Nastepny fragment: "
    r"get_judgment\(id=(\d+), offset=(\d+), limit=(\d+)\)\. "
    r"Pelna tresc: [^\n]*\s*$"
)
_SAOS_ID_RE = re.compile(r"(?m)^ID SAOS\s*:\s*(\d+)\s*$")
SAOS_CHUNK = 20_000


async def _saos_full(native: str, invoke: Invoke) -> str:
    """Assemble the *whole* ruling via SAOS native offset/limit, no local SAOS corpus.

    Every page announces offsets and total source characters. Reject changing
    IDs, missing chunks, duplicate headers and inconsistent final-page markers.
    An oversized ruling or a network error must fail closed to fragment_only.
    """
    if not native.isdecimal():
        raise LookupError("SAOS requires a numeric native judgment identifier")
    source_id = int(native)
    offset = 0
    total = None
    header = None
    parts: list[str] = []

    while True:
        raw = await invoke("saos", "get_judgment", {
            "id": source_id, "offset": offset, "limit": SAOS_CHUNK,
        })
        match = _SAOS_PAGE_RE.search(raw)
        if not match:
            # Compatibility with a source version that provides an unpaginated
            # document; never accept a known-truncated response as complete.
            if offset == 0:
                text, meta = _decode(raw)
                native_id = meta.get("id") or meta.get("document_id")
                if not native_id:
                    raise LookupError("SAOS returned text without verifiable judgment ID")
                if str(native_id).removeprefix("saos:") != str(source_id):
                    raise LookupError("SAOS returned a different judgment identifier")
                return _valid(text)
            raise LookupError("SAOS stopped returning its native pagination metadata")

        begin, end, announced_total = (int(v) for v in match.groups())
        candidate_header = raw[:match.start()]
        identity = _SAOS_ID_RE.search(candidate_header)
        if not identity or int(identity.group(1)) != source_id:
            raise LookupError("SAOS judgment ID did not match the requested ID")
        if header is None:
            header = candidate_header
        elif candidate_header != header:
            raise LookupError("SAOS metadata changed between source pages")
        if (begin != offset or end <= begin or
                end > announced_total or announced_total > MAX_DOC_CHARS):
            raise LookupError("Invalid SAOS source page offsets")
        if total is None:
            total = announced_total
        elif total != announced_total:
            raise LookupError("SAOS total document length changed between calls")

        body = raw[match.end():]
        footer = _SAOS_NEXT_RE.search(body)
        if footer:
            if int(footer.group(1)) != source_id or int(footer.group(2)) != end:
                raise LookupError("SAOS next-page pointer is inconsistent")
            body = body[:footer.start()]
        if len(body) != end - begin:
            raise LookupError("SAOS source page has a gap or unexpected truncation")
        if (end < total) != bool(footer):
            raise LookupError("SAOS failed to declare continuation accurately")
        parts.append(body)
        offset = end
        if end == total:
            break

    source_text = "".join(parts)
    if len(source_text) != total:
        raise LookupError("SAOS assembled document size does not match source metadata")
    return _valid(
        header + f"--- Tresc (znaki 0-{total} z {total} lacznie) ---\n" + source_text
    )


async def _pmi_ruling(hit: dict, invoke: Invoke) -> tuple[str, str, str, str]:
    sig = _signature(str(hit.get("tytul") or hit.get("title") or ""))
    if not sig:
        raise LookupError("Cannot identify an exact case signature for PMI lookup")
    raw = await invoke("pmi", "pmi_get_document", {"document_id": f"ruling:{sig}"})
    content, obj = _decode(raw)
    got = str(obj.get("signature") or "")
    if _fold(got) != _fold(sig):
        raise LookupError(f"PMI returned different signature: {got[:100]}")
    return _valid(content), "full", "pmi", "pmi_get_document"


async def _pmi_article(hit: dict, query: str, invoke: Invoke) -> tuple[str, str, str, str]:
    art = _article(hit, query)
    if not art or not art.lower().startswith("art."):
        raise LookupError("No unambiguous article selector for PMI")
    title = str(hit.get("tytul") or "")
    if not title:
        raise LookupError("No statute title for PMI")
    response = await invoke("pmi", "pmi_search", {"query": title, "kind": "act", "limit": 15})
    try:
        obj = json.loads(response)
    except ValueError as e:
        raise LookupError("Invalid PMI catalogue response") from e
    options = obj.get("results") or []
    exact = [x for x in options if _fold(str(x.get("title") or "")) == _fold(title)]
    if len(exact) != 1:
        raise LookupError("PMI did not uniquely identify the statute")
    slug = str(exact[0].get("slug") or "")
    if not slug:
        identifier = str(exact[0].get("document_id") or "")
        slug = identifier.removeprefix("pmi:act:")
    raw = await invoke("pmi", "pmi_get_article", {"act_slug": slug, "article": art})
    content, data = _decode(raw)
    if data.get("kind") not in (None, "article"):
        raise LookupError("PMI returned something other than an article")
    return _valid(content), "article_only", "pmi", "pmi_get_article"


async def _uodo(hit: dict, native: str, invoke: Invoke) -> tuple[str, str, str, str]:
    docid = native
    if not docid.startswith("PublicDocument-"):
        sig = _uodo_signature(native)
        if not sig:
            raise LookupError("UODO ID cannot be resolved to a case signature")
        raw = await invoke("uodo", "uodo_search_decisions",
                           {"caseNumber": sig, "count": 20, "from": 0})
        docid = ""
        for block in re.split(r"\n\s*---\s*\n", raw):
            actual = re.search(r"(?im)^Sygnatura:\s*(\S+)", block)
            found = re.search(r"(?im)^ID:\s*(PublicDocument-[A-Za-z0-9-]+)", block)
            if actual and found and _fold(actual.group(1)) == _fold(sig):
                docid = found.group(1)
                break
        if not docid:
            raise LookupError("UODO search did not return a document with the same signature")
    raw = await invoke("uodo", "uodo_get_decision", {"id": docid})
    content, _ = _decode(raw)
    return _valid(content), "full", "uodo", "uodo_get_decision"


async def resolve(hit: dict, query: str, invoke: Invoke) -> tuple[str, str, str, str, str]:
    identifier = str(hit.get("document_id") or "").strip()
    prefix, sep, native = identifier.partition(":")
    prefix = prefix.lower() if sep else ""
    if prefix == "ms":
        if not native:
            raise LookupError("Empty MS document identifier")
        raw = await invoke("ms", "ms_get_document", {"document_id": native})
        content, metadata = _decode(raw)
        if (metadata.get("document_id") != identifier or
                metadata.get("identity_verified") is not True or
                metadata.get("content_status") != "full"):
            raise LookupError("Official MS identity/full-text verification missing")
        expected = _signature(str(hit.get("tytul") or hit.get("title") or ""))
        if expected and _fold(expected) != _fold(str(metadata.get("signature") or "")):
            raise LookupError("MS judgment signature differs from Repertorium hit")
        expected_date = str(hit.get("data") or "")[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", expected_date):
            if expected_date != metadata.get("date"):
                raise LookupError("MS judgment date differs from Repertorium hit")
        return _valid(content), "full", "ms", "ms_get_document", ""
    if prefix == "sn":
        content, status, mcp, tool = await _pmi_ruling(hit, invoke)
        return content, status, mcp, tool, ""
    # A missing source may be resolved by an exact PMI signature/article.
    # An EXPLICIT but unsupported namespace (e.g. unknown:) is different: identical
    # signatures may occur in unrelated courts, so PMI cannot prove document identity.
    if prefix and prefix not in {"saos", "nsa", "kio", "uodo", "eli", "eureka",
                                  "celex", "eu-compliance", "pmi"}:
        raise LookupError(
            f"Unsupported source namespace '{prefix}'; identity not verified by PMI"
        )
    if not prefix:
        try:
            content, status, mcp, tool = await _pmi_ruling(hit, invoke)
            return content, status, mcp, tool, ""
        except (LookupError, ValueError):
            content, status, mcp, tool = await _pmi_article(hit, query, invoke)
            return content, status, mcp, tool, _article(hit, query) or ""
    if prefix in {"saos", "nsa", "kio"}:
        source, tool, param = {
            "saos": ("saos", "get_judgment", "id"),
            "nsa": ("nsa", "get_judgment", "doc_id"),
            "kio": ("kio", "kio_get_orzeczenie", "signature_or_id"),
        }[prefix]
        if not native:
            raise LookupError("Empty native document ID")
        arg = int(native) if native.isdecimal() else native
        if prefix == "saos":
            content = await _saos_full(native, invoke)
        else:
            raw = await invoke(source, tool, {param: arg})
            content, _ = _decode(raw)
        return _valid(content), "full", source, tool, ""
    if prefix == "uodo":
        content, status, mcp, tool = await _uodo(hit, native, invoke)
        return content, status, mcp, tool, ""
    if prefix == "pmi":
        raw = await invoke("pmi", "pmi_get_document", {"document_id": native})
        content, obj = _decode(raw)
        kind = obj.get("kind")
        return _valid(content), ("article_only" if kind == "article" else "full"), "pmi", "pmi_get_document", ""
    if prefix == "eli":
        selector = _article(hit, query)
        if not selector:
            raise LookupError("No exact article/paragraph for LEGAL-CITE; full act not requested")
        citation = selector + " " + native
        raw = await invoke("legal-cite", "verify_article", {"citation": citation})
        content, _ = _decode(raw)
        return _valid(content), "article_only", "legal-cite", "verify_article", selector
    if prefix == "celex":
        selector = _article(hit, query)
        if not selector:
            raise LookupError("No exact EU article specified")
        citation = selector + " CELEX " + native.split(":")[0]
        raw = await invoke("legal-cite", "verify_article", {"citation": citation})
        content, _ = _decode(raw)
        return _valid(content), "article_only", "legal-cite", "verify_article", selector
    if prefix == "eu-compliance":
        selector = _article(hit, query)
        if not selector:
            raise LookupError("EU-COMPLIANCE requires a particular article")
        m = _ART.search(selector)
        if not m:
            raise LookupError("No article number for EU-COMPLIANCE")
        raw = await invoke("eu-compliance", "eu_article",
                           {"regulation": native.upper(), "article_number": m.group(1)})
        content, _ = _decode(raw)
        return _valid(content), "article_only", "eu-compliance", "eu_article", selector
    # EUREKA's original get_interpretation only includes ~3000 chars of content,
    # therefore cannot be labelled as full source document.
    if prefix == "eureka":
        raise LookupError("Native EUREKA get_interpretation exposes only a truncated extract")
    raise LookupError(f"No verified resolver for {prefix}")


async def hydrate(payload: dict[str, Any], query: str, invoke: Invoke) -> dict[str, Any]:
    hits = payload.get("trafienia")
    if not isinstance(hits, list):
        raise ValueError("Repertorium JSON has no valid trafienia array")
    semaphore = asyncio.Semaphore(max(1, min(CONCURRENCY, 8)))

    async def one(hit: Any) -> dict:
        if not isinstance(hit, dict):
            return {"fragment": str(hit), "fulltext_status": "fragment_only",
                    "warning": WARNING, "user_disclosure_required": True}
        item = dict(hit)
        identifier = str(hit.get("document_id") or "")
        source = identifier.partition(":")[0].lower() if ":" in identifier else "unresolved"
        text = str(hit.get("fragment") or "")
        status, mcp, tool, selector = "fragment_only", None, None, ""
        reason = None
        async with semaphore:
            try:
                text, status, mcp, tool, selector = await asyncio.wait_for(
                    resolve(hit, query, invoke), timeout=PER_HIT_TIMEOUT)
            except Exception as exc:
                reason = str(exc)[:240] or type(exc).__name__
                if isinstance(exc, TimeoutError):
                    reason = ("Timeout źródła, w tym możliwa zimna konwersja PDF przez LEGAL-CITE. "
                              "Nie jest to dowód braku dokumentu; ponów pobranie.")
        warning = WARNING if status == "fragment_only" else None
        if reason and warning:
            warning += " Powód: " + reason
        body = ("> " + warning + "\n\n" + str(hit.get("fragment") or "")) if warning else text
        try:
            path = await md_store.write(
                hit, source, body, status, mcp, tool, selector, warning)
            item["md_file"] = path
        except (OSError, ValueError) as exc:
            item["write_error"] = str(exc)[:250]
            item["write_failed"] = True
            item["user_disclosure_required"] = True
            item["warning"] = "Nie zapisano odzyskanej treści źródłowej do Markdown; brak md_file."
        item["fulltext_status"] = status
        item["source_mcp"] = mcp
        if warning:
            item["warning"] = warning
            item["user_disclosure_required"] = True
        return item

    enriched = await asyncio.gather(*(one(hit) for hit in hits))
    result = dict(payload)
    result["trafienia"] = enriched
    result["markdown_root"] = md_store.REL_ROOT
    result["fulltext_files"] = sum(1 for h in enriched
                                   if h.get("fulltext_status") in ("full", "article_only")
                                   and h.get("md_file"))
    result["fragment_only"] = sum(1 for h in enriched
                                  if h.get("fulltext_status") == "fragment_only")
    result["instruction"] = (
        "Fragmenty to tylko wyniki wyszukiwania Repertorium. "
        "Pełną treść każdego trafienia odczytaj z md_file (agent) lub "
        "pl_get_document(source='md', document_id=md_file, page=1) (chat). "
        "Jeśli fulltext_status='fragment_only', poinformuj użytkownika, że nie "
        "udało się uzyskać pełnego dokumentu i podano tylko fragment. "
        "Zimna konwersja LEGAL-CITE PDF może potrwać do 90 sekund; "
        "brak odpowiedzi w tym czasie nie dowodzi nieistnienia przepisu."
    )
    return result
