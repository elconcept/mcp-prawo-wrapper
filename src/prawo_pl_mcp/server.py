"""FastMCP server - 4 unified tools nad flota polskich konektorow prawnych.

Uruchamianie:
    python -m prawo_pl_mcp

Lub jako entry point po pip install / uvx:
    prawo-pl-mcp
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from . import hydrate, md_store

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import __version__, audit
from .instructions import INSTRUCTIONS
from .pagination import paginate
from .pool import POOL, SourceUnavailable
from .registry import SOURCES, Source, catalog, get_source
from .coverage import Coverage, build_coverage


# Strukturalne kody bledow - drift test: kazdy kod w INSTRUCTIONS.
class PLLegalError(Exception):
    """Strukturalny blad agregatora - widoczny dla LLM z prefixem [code]."""

    VALID_CODES = frozenset({
        "unknown_source",
        "unknown_tool",
        "invalid_arg",
        "source_unavailable",
        "upstream_error",
    })

    def __init__(self, code: str, message: str):
        if code not in self.VALID_CODES:
            raise ValueError(f"Unknown PLLegalError code: {code}. Valid: {sorted(self.VALID_CODES)}")
        self.code = code
        super().__init__(f"[{code}] {message}")


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    idempotentHint=True,
    destructiveHint=False,
    openWorldHint=True,  # zrodla to zywe API/scraping (poza eu-compliance offline)
)

mcp = FastMCP(name="prawo-pl-mcp", instructions=INSTRUCTIONS)


# ---------- helpers ----------


def _resolve(source: str) -> Source:
    s = get_source(source)
    if s is None:
        raise PLLegalError(
            "unknown_source",
            f"Source '{source}' not in registry. Available: {', '.join(sorted(SOURCES))}. "
            f"Call pl_list_sources for details.",
        )
    return s


def _otel_tag(source_id: str | None) -> None:
    """OTel atrybuty per-call (kanon floty). No-op bez opentelemetry."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attribute("mcp.server", "prawo-pl-mcp")
            if source_id:
                span.set_attribute("mcp.source", source_id)
    except Exception:
        pass


async def _proxy_call(s: Source, tool: str, arguments: dict) -> str:
    """Wywolanie natywnego toola z mapowaniem bledow na kody agregatora."""
    try:
        return await POOL.call(s, tool, arguments)
    except PLLegalError:
        raise
    except SourceUnavailable as exc:
        raise PLLegalError("source_unavailable", str(exc)) from exc
    except Exception as exc:
        msg = str(exc)
        if "unknown tool" in msg.lower() or "tool not found" in msg.lower():
            raise PLLegalError(
                "unknown_tool",
                f"Source '{s.id}' does not expose tool '{tool}'. Native tools: "
                f"{', '.join(s.native_tools)}. Verify via pl_list_sources(source_id='{s.id}').",
            ) from exc
        # Kod bledu konektora (np. [invalid_signature], [not_found]) zostaje w message.
        raise PLLegalError("upstream_error", f"{s.id}/{tool}: {msg}") from exc


def _resolve_page(page: int, page_number: int | None) -> int:
    """Jedna semantyka strony dla calego serwera: `page`, ZAWSZE od 1.

    `page_number` to alias wsteczny (do 0.1.2 tak nazywal sie parametr w
    pl_get_document). Model, ktory nauczyl sie jednej nazwy, nie moze dostac
    ToolError przy drugim toolu - wiec oba dzialaja wszedzie. Sprzecznosc
    (page=3, page_number=7) to blad wywolujacego, nie cicha wygrana jednego.
    """
    if page_number is not None:
        if page != 1 and page != page_number:
            raise PLLegalError(
                "invalid_arg",
                f"page={page} and page_number={page_number} disagree. Use `page` only "
                f"(`page_number` is a deprecated alias kept for backward compatibility).",
            )
        page = page_number
    if page < 1:
        raise PLLegalError("invalid_arg", f"page is 1-based; got {page}")
    return page


def _coerce_arguments(arguments: Any, args: Any) -> dict:
    """`arguments` kanoniczne, `args` alias - plus tolerancja na JSON w stringu."""
    provided = [(n, v) for n, v in (("arguments", arguments), ("args", args)) if v is not None]
    if not provided:
        return {}
    if len(provided) == 2:
        raise PLLegalError(
            "invalid_arg",
            "pass either `arguments` or `args` (alias of the same field), not both.",
        )
    name, value = provided[0]
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise PLLegalError(
                "invalid_arg", f"`{name}` is a string that is not valid JSON: {exc}"
            ) from exc
    if not isinstance(value, dict):
        raise PLLegalError(
            "invalid_arg",
            f"`{name}` must be an object mapping the native tool's parameter names to "
            f"values, got {type(value).__name__}.",
        )
    return value


def _looks_like(provided: str, known: str) -> bool:
    """Czy `provided` to prawdopodobnie literowka/skrot nazwy `known`."""
    a, b = provided.lower(), known.lower()
    if a == b:
        return True
    if a.replace("_", "") == b.replace("_", ""):
        return True
    return len(a) >= 3 and (b.startswith(a) or a.startswith(b))


async def _validate_native_args(s: Source, tool: str, args: dict) -> None:
    """Bramka pass-through: zlap zla nazwe parametru ZANIM poleci do konektora.

    Dotad natywna nazwa (np. `article_number` przy eu_article) zdradzala sie
    dopiero w bledzie upstreamu. Zakres celowo waski: brak pola wymaganego oraz
    nazwa bliska znanej (literowka). Nieznane pola bez podobienstwa przepuszczamy
    - konektory floty swiadomie akceptuja nadmiarowe pola (forward-compat).
    """
    try:
        tools = await POOL.list_tools(s, use_cache=True)
    except SourceUnavailable as exc:
        raise PLLegalError("source_unavailable", str(exc)) from exc

    spec = next((t for t in tools if t.get("name") == tool), None)
    if spec is None:
        raise PLLegalError(
            "unknown_tool",
            f"Source '{s.id}' does not expose tool '{tool}'. Native tools: "
            f"{', '.join(sorted(t.get('name', '') for t in tools))}.",
        )
    schema = spec.get("input_schema") or {}
    properties = schema.get("properties") or {}
    if not properties:
        return  # konektor nie deklaruje schematu - nie ma czego egzekwowac

    known = set(properties)
    required = [p for p in (schema.get("required") or []) if p not in args]
    unknown = [k for k in args if k not in known]
    near_miss = {
        k: [n for n in known if _looks_like(k, n)] for k in unknown
    }
    near_miss = {k: v for k, v in near_miss.items() if v}

    if not required and not near_miss:
        return

    parts = [f"Tool '{tool}' of source '{s.id}': "]
    if required:
        parts.append(f"missing required {required}. ")
    for bad, candidates in near_miss.items():
        parts.append(f"'{bad}' is not a parameter - did you mean {candidates}? ")
    parts.append(f"Accepted parameters: {sorted(known)}.")
    raise PLLegalError("invalid_arg", "".join(parts))


def _audited(tool: str, source_id: str | None, params: Any, started: float,
             summary: dict, error: str | None = None) -> None:
    audit.log_event(
        tool=tool,
        source=source_id,
        params=params,
        result_summary=summary,
        latency_ms=(time.monotonic() - started) * 1000,
        error=error,
    )


@mcp.tool(annotations=READ_ONLY)
async def pl_coverage() -> Coverage:
    """Declare what this connector covers, how it is sourced, and what it does NOT cover.

    Call this before telling a user that the law "does not contain" something, and whenever
    a search comes back empty: the absence may be a gap in this connector rather than in the
    law. Every gap carries a fallback saying where to look instead.

    Returns:
        ``Coverage`` with families, an as-of note, and a non-empty list of known gaps.
    """
    started = time.monotonic()
    coverage = build_coverage()
    _audited("pl_coverage", None, {}, started,
             {"families": len(coverage.families), "gaps": len(coverage.known_gaps)})
    return coverage


# ---------- unified tools ----------


async def pl_list_sources(source_id: str | None = None, group: str | None = None) -> str:
    """List available Polish/EU legal data sources, or inspect one source's live tool schemas.

    Without arguments: full catalog (id, coverage, capabilities, native tool names,
    and `native_params` - the NATIVE parameter name each unified parameter maps to,
    e.g. eu-compliance pl_get_document -> {"tool": "eu_article",
    "document_id": "article_number"}) - reads a local registry, spawns nothing.
    With `source_id`: connects to that connector (lazy spawn on first use) and
    returns its live tools/list with input schemas - needed for native tools that
    the unified tools do not cover. Optional `group` filter: 'pl' or 'eu'.

    Errors: `unknown_source` (bad source_id), `source_unavailable` (connector
    could not start).
    """
    started = time.monotonic()
    _otel_tag(source_id)
    if source_id is None:
        if group is not None and group not in ("pl", "eu"):
            raise PLLegalError("invalid_arg", "group must be 'pl' or 'eu'")
        result = {
            "server": f"prawo-pl-mcp {__version__}",
            "sources": catalog(group),
            "hint": "pl_search / pl_get_document for the common path; "
            "pl_call for source-specific tools (key its `arguments` by the native "
            "names in `native_params`); pl_list_sources(source_id=...) for the "
            "live schema of every native tool. `page` is 1-based everywhere.",
        }
        _audited("pl_list_sources", None, {"group": group}, started, {"sources": len(result["sources"])})
        return json.dumps(result, ensure_ascii=False, indent=1)

    s = _resolve(source_id)
    try:
        tools = await POOL.list_tools(s)
    except SourceUnavailable as exc:
        _audited("pl_list_sources", s.id, {"source_id": source_id}, started, {}, error=str(exc))
        raise PLLegalError("source_unavailable", str(exc)) from exc
    _audited("pl_list_sources", s.id, {"source_id": source_id}, started, {"tools": len(tools)})
    return json.dumps({"source": s.id, "tools": tools}, ensure_ascii=False, indent=1)


async def _invoke_native(source: str, tool: str, arguments: dict) -> str:
    return await _proxy_call(_resolve(source), tool, arguments)


async def pl_search(
    source: str = "repertorium",
    query: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    limit: int | None = None,
    extra: dict | None = None,
    page_number: int | None = None,
) -> str:
    """Unified search across any registered source (SAOS, NSA, ISAP, EUREKA, KIO, UODO...).

    Common parameters are translated to the source's native names (dateFrom vs
    date_from, 0- vs 1-based pages - handled here; `page` is ALWAYS 1-based, and
    is the same parameter name in pl_get_document). `date_from`/`date_to`:
    YYYY-MM-DD. `limit`: results per page (clamped to the source maximum).
    `extra`: source-specific native filters merged verbatim (e.g.
    {"courtType": "SUPREME"} for saos, {"country": "es"} for legalize - the
    native names are listed under `native_params` in pl_list_sources).
    `page_number` is a deprecated alias of `page`; prefer `page`.

    Errors: `unknown_source`, `invalid_arg` (source has no search tool, e.g. krs;
    missing required extra; page < 1), `source_unavailable`, `upstream_error`
    (connector's own error code preserved in message).
    """
    started = time.monotonic()
    s = _resolve(source)
    _otel_tag(s.id)
    spec = s.search
    if spec is None:
        raise PLLegalError(
            "invalid_arg",
            f"Source '{s.id}' has no search tool ({s.notes or 'lookup by identifier only'}). "
            f"Use pl_get_document or pl_call.",
        )
    page = _resolve_page(page, page_number)

    args: dict[str, Any] = dict(extra or {})
    missing = [p for p in spec.required_extra if p not in args]
    if missing:
        raise PLLegalError(
            "invalid_arg",
            f"Source '{s.id}' search requires extra={{{', '.join(repr(m) for m in missing)}: ...}}. "
            f"See pl_list_sources(source_id='{s.id}').",
        )
    if query is not None and spec.query_param:
        args.setdefault(spec.query_param, query)
    if date_from is not None:
        if not spec.date_from_param:
            raise PLLegalError(
                "invalid_arg",
                f"Source '{s.id}' does not support date filtering ({s.notes or 'no date params'}).",
            )
        args.setdefault(spec.date_from_param, date_from)
    if date_to is not None and spec.date_to_param:
        args.setdefault(spec.date_to_param, date_to)
    if spec.page_param:
        args.setdefault(spec.page_param, page - 1 if spec.page_base == 0 else page)
    if s.id == "uodo" and page > 1:
        args.setdefault("from", (page - 1) * (limit or 10))
    if limit is not None and spec.size_param:
        clamped = limit
        if spec.size_max:
            clamped = min(clamped, spec.size_max)
        if spec.size_min:
            clamped = max(clamped, spec.size_min)
        args.setdefault(spec.size_param, clamped)

    if s.id == "repertorium":
        args["format"] = "json"
    try:
        text = await _proxy_call(s, spec.tool, args)
        if s.id == "repertorium":
            try:
                result = json.loads(text)
            except ValueError as exc:
                raise PLLegalError("upstream_error", "Repertorium did not return JSON") from exc
            enriched = await hydrate.hydrate(result, query or "", _invoke_native)
            text = json.dumps(enriched, ensure_ascii=False)
    except PLLegalError as exc:
        _audited("pl_search", s.id, args, started, {}, error=exc.code)
        raise
    _audited("pl_search", s.id, args, started, {"chars": len(text)})
    return text


async def pl_get_document(
    source: str,
    document_id: str,
    page: int = 1,
    extra: dict | None = None,
    page_number: int | None = None,
    refresh: bool = False,
) -> str:
    """Page the stored Markdown source or fetch a native MCP document on demand.

    source='md' accepts md_file from pl_search. No PostgreSQL, local SAOS
    SQLite dump, or in-wrapper PDF extraction is used. For LEGAL-CITE supply
    the concrete article citation, not the identifier of an entire act.
    Cold conversion of a PDF by LEGAL-CITE may take ~90 seconds.
    """
    started = time.monotonic()
    page = _resolve_page(page, page_number)
    if source == "md":
        try:
            out = await md_store.read(document_id, page)
        except (OSError, ValueError) as exc:
            raise PLLegalError("invalid_arg", str(exc)) from exc
        _audited("pl_get_document", "md", {"file": document_id, "page": page},
                 started, {"total_chars": out["total_chars"], "page": out["page"]})
        return json.dumps(out, ensure_ascii=False)

    extra = dict(extra or {})
    if source in ("auto", "repertorium"):
        prefix, sep, value = document_id.partition(":")
        if not sep:
            raise PLLegalError("invalid_arg", "Auto lookup requires a source-prefixed document_id")
        if prefix == "eli":
            source = "legal-cite"
            document_id = str(extra.pop("citation", ""))
            if not document_id:
                raise PLLegalError(
                    "invalid_arg",
                    "A specific article is required, e.g. extra={'citation': 'art. 23 DU/2024/917'}; "
                    "or use source='md' and md_file returned by pl_search.",
                )
        elif prefix == "sn":
            source = "pmi"
            signature = extra.pop("signature", None)
            if not signature:
                raise PLLegalError(
                    "invalid_arg", "SN requires an exact signature in extra or a saved md_file.")
            document_id = "ruling:" + str(signature)
        else:
            source, document_id = prefix, value
    elif document_id.startswith(source + ":"):
        document_id = document_id[len(source) + 1:]

    s = _resolve(source)
    _otel_tag(s.id)
    spec = s.get
    missing = [p for p in spec.required_extra if p not in extra]
    if missing:
        raise PLLegalError("invalid_arg", f"Source '{s.id}' requires extra={missing}. {spec.id_hint}")
    arguments = dict(extra)
    arguments.setdefault(spec.id_param, int(document_id) if
                         s.id in {"saos", "kio"} and document_id.isdecimal()
                         else document_id)
    if spec.page_param:
        arguments.setdefault(spec.page_param, page)
    try:
        if s.id == "uodo":
            content, _, _, _ = await hydrate._uodo(
                {"document_id": "uodo:" + document_id}, document_id, _invoke_native)
            metadata = {}
        else:
            raw = await _proxy_call(s, spec.tool, arguments)
            content, metadata = hydrate._decode(raw)
            content = hydrate._valid(content)
    except (LookupError, ValueError) as exc:
        raise PLLegalError("upstream_error", str(exc)) from exc

    if spec.page_param:
        out = {"content": content, "page": page, "page_number": page,
               "pagination": "native", "total_chars": len(content)}
    else:
        out = paginate(content, page)
        out["page"] = out["page_number"]
        out["pagination"] = "aggregator"
    out.update({
        "source": s.id,
        "document_id": (("eli:" + document_id) if s.id == "legal-cite"
                        else s.id + ":" + str(document_id)),
        "origin": "connector",
        "complete": s.id not in {"eureka", "eu-sparql"},
    })
    if metadata.get("source_url"):
        out["source_url"] = metadata["source_url"]
    if s.id == "legal-cite":
        out["content_status"] = "article_only"
        out["notice"] = (
            "Cold PDF processing can take up to 90 seconds. A timeout is not "
            "evidence that this provision does not exist; retry as needed."
        )
    if s.id in {"eureka", "eu-sparql"}:
        out["warning"] = (
            "Native MCP may provide only an extract or metadata, not confirmed full text."
        )
    _audited("pl_get_document", s.id, {"document_id": document_id, "page": page},
             started, {"total_chars": out["total_chars"], "page": page})
    return json.dumps(out, ensure_ascii=False)


async def pl_call(
    source: str,
    tool: str,
    arguments: dict | str | None = None,
    args: dict | str | None = None,
) -> str:
    """Escape hatch: call any native tool of any registered source.

    For operations the unified tools do not cover: citator (saos_cite_check),
    DPA statistics (uodo_stats), procurement-article search (kio_by_pzp_article),
    board composition (get_board), regulation comparison (eu_compare), tax
    category dictionary (list_categories)... `arguments` (alias: `args` - both
    accepted, pass only one) is an object keyed by the NATIVE parameter names of
    that tool, passed verbatim. The native names of the common ones are in
    `native_params` from pl_list_sources; for everything else read the live
    schema via pl_list_sources(source_id=...). Wrong parameter names are caught
    here against the connector's schema, before the call leaves the aggregator.

    Errors: `unknown_source`, `unknown_tool` (not exposed by that source),
    `invalid_arg` (missing required or misspelled parameter name),
    `source_unavailable`, `upstream_error` (connector's own error code in message).
    """
    started = time.monotonic()
    s = _resolve(source)
    _otel_tag(s.id)
    args = _coerce_arguments(arguments, args)
    try:
        await _validate_native_args(s, tool, args)
        text = await _proxy_call(s, tool, args)
    except PLLegalError as exc:
        _audited("pl_call", s.id, {"tool": tool, **args}, started, {}, error=exc.code)
        raise
    _audited("pl_call", s.id, {"tool": tool, **args}, started, {"chars": len(text)})
    return text


for _tool in (pl_list_sources, pl_get_document, pl_call):
    mcp.tool(_tool, annotations=READ_ONLY)
# pl_search now persists source Markdown in the explicitly mounted legal directory.
mcp.tool(pl_search, annotations=ToolAnnotations(
    readOnlyHint=False, idempotentHint=True, destructiveHint=False, openWorldHint=True,
))


def main() -> None:
    """Entry point stdio."""
    try:
        mcp.run()
    finally:
        try:
            asyncio.run(POOL.close_all())
        except Exception:
            pass


if __name__ == "__main__":
    main()
