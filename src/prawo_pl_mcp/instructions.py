"""Procedural orchestration - wstrzykiwane do system promptu klienta MCP.

LLM widzi to PRZED pierwszym tool call. Pattern z dograh v1.31.0 via flota
matematicsolutions. Drift test (tests/test_instructions_drift.py) failuje jesli
tool wymieniony tutaj nie jest zarejestrowany lub kod bledu nieudokumentowany.

Zasady: call order, twarde ograniczenia, iteracja po bledach, styl. NIE
re-enumerujemy sygnatur tooli (sa w tools/list) ani szczegolow zrodel
(sa w pl_list_sources - zero driftu przy dodaniu zrodla do registry).
"""

INSTRUCTIONS = """\
One MCP server for Polish legal data. Aggregates independent MCP connectors
(case law, legislation, company register, tax rulings, public procurement,
data-protection decisions + optional EU corpus) behind 4 unified tools.
Existing remote MCP services are preferred when PRAWO_PL_MCP_URL_<SOURCE> is configured; other connectors retain on-demand subprocesses. Repertorium is remote-only and must point to its already running instance.

## Call order

0. For EVERY NEW general legal research question, call `pl_find` FIRST,
   without choosing SAOS/NSA/ISAP yourself. It queries the actual Repertorium
   semantic aggregator across normative acts, judgments and decisions; results
   include native document_ref, excerpts and source URLs.
   A semantic hit is a lead to the correct source, NOT a substitute for
   reading full text. Never pretend an unavailable semantic service returned 0.
1. Use `pl_get_by_ref` for the full text of an identified hit, e.g.
   saos:166511 or eli:DU/2024/917. It routes by Repertorium's document_id prefix;
   DO NOT infer the backend from a URL (SAOS hits can link to orzeczenia.ms.gov.pl
   or www.sn.pl).
2. Expert override `pl_list_sources` - start here. Without arguments: catalog of sources
   (id, coverage, capabilities, native tools) plus `native_params` - the native
   parameter name each unified parameter maps to for that source. With
   `source_id`: live tool schemas of that connector - check before using
   `pl_call` or source-specific `extra` parameters.
3. `pl_search` - unified search across any source. Common parameters
   (`query`, `date_from`, `date_to`, `page`, `limit`) are translated to the
   source's native names; pass source-specific filters via `extra` (native
   names, see `native_params` or `pl_list_sources(source_id=...)`).
4. `pl_get_document` - full document by source + identifier (judgment ID or
   case signature, ELI, KRS number, interpretation ID...). Long documents are
   paginated at ~5000 characters per page; iterate `page` while `has_more` is
   true. Sources that paginate server-side report `pagination` = "native" and
   put their own page counter in the text.
5. `pl_call` - escape hatch: any native tool of any source (citator checks,
   statistics, board composition, dictionaries...). Use when unified tools do
   not cover the operation. Verify the schema first via
   `pl_list_sources(source_id=...)`.

## One name per concept

- `page` is the page parameter of BOTH `pl_search` and `pl_get_document`, and it
  is ALWAYS 1-based. `page_number` is a deprecated alias accepted by both -
  never mix the two in one call.
- `pl_call` takes the native tool's parameters in `arguments` (alias: `args`,
  pass only one). Key it by NATIVE names - `native_params` in `pl_list_sources`
  lists the common ones (e.g. eu-compliance article lookup wants
  `article_number`, not `article`). A wrong name comes back as `invalid_arg`
  naming the accepted parameters, before the call reaches the connector.

## Hard constraints

- Do not answer past the edge of this federation: this server holds no corpus of
  its own. When a search comes back empty, call `pl_coverage` and relay what it
  says is missing. Absence here is not absence in Polish law.
- Legal answers require documents, not search snippets: after `pl_find` or `pl_search`,
  fetch the actual text with `pl_get_document` before quoting or reasoning.
- NEVER invent case signatures, ELI identifiers, KRS numbers or dates - use
  only values returned by tools. Quote verbatim from document content.
- Always cite: source name + identifier + date + source URL when returned.
- Each source enforces its own rate limits - do not send bursts of parallel
  queries to one source.
- All tools are read-only; no tool mutates any upstream system.
- Audit log JSONL: every call is logged to ~/.matematic/audit/prawo-pl-mcp.jsonl
  (no document content).

## Iterating on errors

Errors carry a `[code]` prefix:
- `unknown_source` - source id not in registry. Call `pl_list_sources` and retry.
- `unknown_tool` - native tool name not exposed by that source (pl_call).
  Check `pl_list_sources(source_id=...)`.
- `invalid_arg` - parameter out of range or missing. Fix per message and retry.
- `source_unavailable` - existing remote MCP is unconfigured/unreachable, or connector could not start (missing Node/uv runtime or
  package unreachable). Report to the user with the message hint; other sources
  keep working - consider an alternative source.
- `upstream_error` - the connector itself errored (its own [code] is preserved
  in the message, e.g. invalid_signature, not_found). Follow the inner message;
  retry once if it looks transient.

## Style

- Present results with full citations (signature + date + court/body).
- When comparing case law across sources (e.g. SAOS vs NSA), state which
  database each ruling comes from.
- Administrative-court matters: prefer the NSA source; general courts and
  Supreme Court: SAOS. Statutes: ISAP. If unsure, check coverage in
  `pl_list_sources`.
- Disclaimer where relevant: court rulings are not a source of law in Poland
  (art. 87 of the Constitution) - reference material, not binding precedent.
"""
