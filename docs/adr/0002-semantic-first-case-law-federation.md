# ADR 0002 — Semantic-first case-law federation behind one MCP

Status: **proposed / pilot** (18 October 2026).
Existing ADR 0001 ("proxy, not monorepo") continues to apply.

## Decision

Extend **this** wrapper rather than turning \`mcp-saos\` into a dependency-heavy
merger or forcing an LLM to call Repertorium, SAOS, NSA and MS individually.
Do not remove existing \`pl_search\`, \`pl_get_document\`, \`pl_call\` or any
standalone connectors from LEX MCP Portal during the pilot.

### Desired client API

Expose one **MCP server** and a common public workflow:

- `pl_find(query, domain=auto, jurisdiction=auto, deep=false)`
- `pl_get_by_ref(document_ref, page=1)`

The single reference `source:id` identifies the source and provider ID;
all source links are retained, and long text is paginated.

Internal domain routers under `pl_find`: case law (`find_case_law` from
this PR), Polish legislation (Repertorium -> official ISAP/ELI), EU
legislation/CJEU (Repertorium -> EU SPARQL/EUR-Lex) and dedicated KRS/UODO
adapters when the user asks about those subjects. Do not confuse an act
with a judgment. Repertorium is a lead generator, not a completeness filter.

The existing source-specific `pl_search`, `pl_get_document`, `pl_call`
remain backward-compatible expert interfaces. This draft includes the
case-law routing core; universal MCP tools and live adapter wiring are
**not yet deployed**.
### Case-law search flow

1. **Repertorium** semantic search (short deadline, optional; never a source
   of truth or proof of absence). Its snippets, document IDs and deep links
   are navigation leads. Resolve through an authoritative source before
   quoting or claiming that a document exists in a given corpus.
2. **SAOS adapter**: existing \`mcp-saos\` code handles its own versioned local
   dump and official SAOS API fallback. Do not create another downloader or
   touch \`saos.db\` here.
3. **NSA/WSA**: existing \`mcp-nsa\`, especially for administrative matters.
   If the court is known common, skip NSA; if known administrative, search NSA
   directly. Mixed/unspecified research searches both, because SAOS doesn't
   cover administrative courts.
4. **MS discovery cache**, physically stored ONLY by the MS adapter in
   \`ms-discovered.sqlite\`. Search previously verified MS metadata/FTS records
   before live scraping.
5. **MS live portal**, only on remaining misses or when \`deep=true\`.
   Live HTML/RSS parser from \`prawo-pl-orzeczenia-ms\` (pilot under
   \`elconcept/mcp-saos/ms-mcp\`), no headless browser needed by default.
   It publishes **only a selection** of common-court rulings; recent full
   texts may be unavailable. An error is never a proof of zero results.

The pure routing/combination component is
\`src/prawo_pl_mcp/case_law_federation.py\`. Its adapter boundary permits
unit testing without networking; live MCP adapters and the public tool entry
points are separate deployment gates.

### Merge policy

- Prefer provider-native identity. In a **cross-provider** merge, require
  court + signature + judgment date + document type all to match
  consistently; preserve every provider's ID and URL.
- Do not merge rulings merely because the same case signature appears.
  One case can produce different rulings, corrections and justifications.
- Snippet-only results must have \`full_text_available=false\`. A semantic
  snippet does not satisfy a request for verbatim full text.
- Keep publication date distinct from judgment date and enforce source
  confidence/provenance in the response.
- Upstream errors, rate limits, login challenges, incomplete metadata,
  and partial-index coverage must appear explicitly, not as "0 records".

### Storage ownership

| Owner | DB | Writes |
|---|---|---|
| mcp-saos | versioned SAOS dump | scheduled full-resume + incremental sync only |
| mcp-orzeczenia-ms | MS discovery SQLite+FTS5 | validated successful live lookups and document reads |
| mcp-nsa | CBOSA live | read-only; optional separately scoped cache in a later phase |
| mcp-prawo-wrapper | none | no normalized corpus copies |

The MS discovery index is **opportunistic**, not an attempt to silently crawl
the million missing judgments. Rows contain source ID, URL, court, signature,
judgment date, **separate** publication date, snippet, optional full text,
and last source-observed timestamp. The original SAOS updater never scans or
mutates that database.

### Availability and latency

- Semantic lookup MUST have a short timeout / circuit-breaker. The current
  Repertorium MCP's 100-retry behavior is not suitable for blocking every
  source lookup; failure cannot abort the remaining chain.
- Source backends use their respective upstream limits. Avoid bursts of
  requests, block attempts to circumvent access controls, and never present
  a challenge as a legitimate empty result.
- Well-identified court-type routes skip irrelevant sources to reduce calls.
- \`deep\` requests broader coverage but are slower and still cannot claim
  exhaustive knowledge of court activity.
- On no evidence return \`not_found_in_checked_sources\`, never
  \`judgment_does_not_exist\`.

### Universal search integration gates

1. [x] \`mcp-saos\` live fallback prevents false empty responses (PR #3 merged).
2. [x] Create independent pilot MS MCP with 6 tools (draft PR #4).
3. [x] Add MS-discovery SQLite FTS cache separate from SAOS (draft PR #4).
4. [x] Implement source-neutral routing/dedup core + offline tests here.
5. [ ] Normalizing adapters: Repertorium, SAOS (use structured citations),
   NSA (use structured citations), MS cache/live (use structured JSON).
6. [ ] Wire \`pl_find_case_law\` / \`pl_get_case_law\` with those adapters.
7. [ ] Provide service-to-service auth for existing upstream MCP endpoints
   and check no unauthenticated access; no direct port exposure.
8. [ ] Live acceptance tests: (a) present SAOS; (b) absent SAOS, present MS;
   (c) administrative NSA; (d) ambiguous signature across courts;
   (e) unavailable Repertorium; (f) broken recent MS full-text;
   (g) both source errors -> partial, never definitive zero.
9. [ ] After deploying new wrapper, register ONLY the unified search/get
   surface in the client. Keep native tools behind \`pl_call\` or LEX Portal
   for power use without forcing model-led multi-call research.

## Alternatives rejected

- SAOS itself calls NSA and MS: couples a stable local mirror to live
  scrapers; risks disrupting SAOS incremental sync.
- Physically union all rows into the SAOS SQLite database: different origin,
  lifecycle and schema; repeated incremental updates will conflict.
- Use semantic Repertorium as an exhaustive filter: false negatives and
  unbounded retries may suppress real official-source results.
- A new monorepo with copies of other connectors: violates ADR 0001,
  duplicates deploy/auth and increases drift.
