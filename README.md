# prawo-pl-mcp

<!-- mcp-name: io.github.matematicsolutions/prawo-pl-mcp -->

One MCP server for Polish legal data.

Independent legal MCP services - case law, statutes, tax interpretations, registers,
data-protection decisions and EU law - behind five unified tools. On Synology
they run as separate Portainer stacks accessed through internal Streamable HTTP;
stdio (npx/uvx) remains available for standalone use. The wrapper is not a
second search engine or a store of embedded case-law documents.

"Prawo" is Polish for "law"; the name follows yargi-mcp's move of naming a
country server in its own language.

## Why an aggregator

The connectors cover Polish legal data well, but as separate MCP servers, one
per database - ten installs and ten config entries before the first question.
[yargi-mcp](https://github.com/saidsurucu/yargi-mcp) showed the fix for
Turkish law: 16 institutions, one server. prawo-pl-mcp does the same for Poland:

- Five tools instead of 42. `pl_list_sources`, `pl_search`, `pl_get_document`,
  `pl_call` and `pl_coverage` - fewer tool schemas means less context spent before the LLM starts
  working.
- One convention. The connectors grew organically: `dateFrom` here, `date_from`
  there, pages counted from 0 or from 1 depending on the repo. Here `page` is
  always 1-based and dates are always `date_from`/`date_to` (YYYY-MM-DD); the
  translation happens inside. One name per concept applies to the aggregator's
  own tools too: `page` is the page parameter of both `pl_search` and
  `pl_get_document` (`page_number` still works as a deprecated alias), and
  `pl_call` takes `arguments` or its alias `args`.
- Native names on the table. Every catalog entry carries `native_params` - the
  native parameter name each unified one maps to for that source, so
  `article_number` (eu-compliance) is visible without spawning the connector or
  reading an upstream error. `pl_call` checks the names it was given against
  the connector's own schema and says which one it meant.
- Existing MCPs are reused. Configure `PRAWO_PL_MCP_URL_<ID>` for internal
  Streamable HTTP sources. A source that cannot be reached reports an error
  while other sources remain usable. Standalone npx/uvx runtimes remain optional.
- Repertorium-first retrieval. Default `pl_search` requests native
  `format=json`, preserves every original search snippet, and attempts to
  retrieve each identified document using its proper MCP. The full retrieved
  text goes to a separate Markdown file, never inline in search results.
  An unresolved record remains a `fragment_only` hit with mandatory disclosure.
- Bounded Markdown reading. `pl_get_document(source="md", document_id=md_file)`
  paginates the saved content at roughly 5000 characters/page and verifies
  its SHA-256. A stable digest can be passed between pages to detect updates.
  This is a source-file store, not an in-wrapper full-text database.

## Coverage

| Source id | What | Institution / database | Connector | Runtime |
|---|---|---|---|---|
| `saos` | Case law: common courts, Supreme Court, Constitutional Tribunal + citator | [SAOS](https://www.saos.org.pl) | [mcp-saos](https://github.com/matematicsolutions/mcp-saos) | npx |
| `nsa` | Case law: administrative courts (NSA + 16 WSA) | [CBOSA](https://orzeczenia.nsa.gov.pl) | [mcp-nsa](https://github.com/matematicsolutions/mcp-nsa) | npx |
| `legal-cite` | Exact statutory articles, including PDF-only Dz.U. | ELI/Dz.U. | LEGAL-CITE (independent MCP) | http |
| `krs` | Company register: extracts, history, board composition | [KRS API (Ministry of Justice)](https://api-krs.ms.gov.pl) | [mcp-krs](https://github.com/matematicsolutions/mcp-krs) | npx |
| `ustawy` | 37 statutes: article wording from the consolidated text and commentary to every article | commentary repos (grounding-prawo) | `mcp-ustawy` (remote, `PRAWO_PL_MCP_URL_USTAWY`) | http |
| `kio` | Public procurement: National Appeal Chamber rulings | [orzeczenia.uzp.gov.pl](https://orzeczenia.uzp.gov.pl) | [kio-orzeczenia-mcp](https://github.com/matematicsolutions/kio-orzeczenia-mcp) | uvx |
| `uodo` | GDPR enforcement: Polish DPA decisions, fines, stats | [orzeczenia.uodo.gov.pl](https://orzeczenia.uodo.gov.pl) | [uodo-orzeczenia-mcp](https://github.com/matematicsolutions/uodo-orzeczenia-mcp) | uvx |
| `eu-sparql` | EU law: EUR-Lex by CELEX, CJEU by ECLI, GDPRhub | [Cellar SPARQL](https://op.europa.eu/en/web/cellar) | [mcp-eu-sparql](https://github.com/matematicsolutions/mcp-eu-sparql) | npx |
| `eu-compliance` | 14 EU regulations offline (GDPR, AI Act, DORA, NIS2...) | Standalone source SQLite corpus | [mcp-eu-compliance](https://github.com/matematicsolutions/mcp-eu-compliance) | npx/http |
| `repertorium` | Semantic Polish case-law discovery with original snippets | Repertorium | mcp-repertorium | http |
| `pmi` | Exact ruling by signature and published act/article HTML | prawmi.pl | PMI (separate local MCP) | http |
| `eureka` | Tax interpretation search and retrieval (may return excerpt) | EUREKA | [mcp-eureka](https://github.com/matematicsolutions/mcp-eureka) | npx/http |
| `md` | Files successfully saved beneath the dedicated legal sources directory | `PRAWO_MD_DIR` | Local read-only document source | local |

Polish sources are tagged `group: pl`, EU extras `group: eu` - filter with
`pl_list_sources(group="pl")`.

## Tools

| Tool | What it does |
|---|---|
| `pl_list_sources` | Catalog of sources (no subprocess spawned). With `source_id`: live tool schemas of one connector. |
| `pl_search` | Repertorium by default; returns original snippets + `fulltext_status` + actually saved `md_file`, or direct native search for explicit `source`. |
| `pl_get_document` | Paginates saved Markdown (`source=md`) or retrieves a native document/article by exact identifier. |
| `pl_call` | Any native tool of any connector: citator, DPA statistics, board composition, regulation comparison... |
| `pl_coverage` | Declare what this connector covers, when each family was captured, and - explicitly - what it does NOT cover. Every gap carries a fallback. |

The typical flow an LLM follows (spelled out in the server's `instructions`):
`pl_list_sources` → `pl_search` → `pl_get_document`, with `pl_call` for the
specialized tools each connector brings.

## Install

Requires Python ≥ 3.11 plus the runtimes of the sources you use: Node.js ≥ 18
for `npx` sources, [uv](https://docs.astral.sh/uv/) for `uvx` sources. If a
runtime is missing, its sources report `source_unavailable` and the rest work.

### Claude Code

```bash
claude mcp add pl-legal -- uvx prawo-pl-mcp
```

### Claude Desktop / any MCP client (stdio)

```json
{
  "mcpServers": {
    "pl-legal": {
      "command": "uvx",
      "args": ["prawo-pl-mcp"]
    }
  }
}
```

### Remote (Streamable HTTP)

```bash
uvicorn prawo_pl_mcp.asgi:app --host 0.0.0.0 --port 8000
```

Open by default (public, read-only data). Set `PRAWO_PL_MCP_API_KEY` to require
`X-API-Key: <key>` or `Authorization: Bearer <key>` on every request.

## Configuration

| Env | Default | Meaning |
|---|---|---|
| `PRAWO_PL_MCP_SOURCES` | - | Comma list of exposed sources, e.g. `saos,nsa,ustawy`; empty = all. |
| `PRAWO_PL_MCP_URL_<ID>` | - | Use an already deployed MCP server (Streamable HTTP) for a source instead of spawning it, e.g. `PRAWO_PL_MCP_URL_SAOS=http://10.0.10.201:8402/mcp`. Required for `http` sources. |
| `PRAWO_PL_MCP_CMD_<ID>` | - | Override the spawn command for a source, e.g. `PRAWO_PL_MCP_CMD_SAOS="node C:/dev/mcp-saos/dist/index.js"` for a local checkout. `<ID>` = source id, uppercase, `-` → `_`. |
| `PRAWO_PL_MCP_INIT_TIMEOUT` | `180` | Seconds allowed for a connector's first start (includes package download). |
| `PRAWO_PL_MCP_TIMEOUT` | `90` | Default seconds per MCP source call. |
| `PRAWO_PL_MCP_TIMEOUT_LEGAL_CITE` | unset | Override for PDF cold processing (NAS config: 240s). A timeout is not a negative verification. |
| `PRAWO_MD_DIR` | `/legal_sources` | Dedicated, writable bind mount for generated legal-source Markdown; never mount the whole legal repository. |
| `PRAWO_HYDRATE_TIMEOUT` | `250` | Per-Repertorium-hit hydration deadline in seconds. |
| `PRAWO_HYDRATE_CONCURRENCY` | `3` | Maximum concurrent full-text retrieval attempts. |
| `PRAWO_PL_MCP_AUDIT_DIR` | `~/.matematic/audit` | Where the JSONL audit log goes. |
| `PRAWO_PL_MCP_API_KEY` | - | ASGI mode only: require this API key (dual-channel). |

## Architecture

The aggregator follows the upstream proxy architecture
([ADR 0001](docs/adr/0001-proxy-nie-monorepo.md)). Connectors are not
vendored; the wrapper uses their MCP endpoints. Repertorium results may
additionally be hydrated into individual Markdown source files in a dedicated
bind mount. No local embedding index, PostgreSQL full-text cache or SAOS dump
is needed by the wrapper. The separate EU-COMPLIANCE MCP retains its own
version-pinned corpus.

```
LLM client ──MCP──▶ prawo-pl-mcp ──MCP/HTTP──▶ Repertorium (semantic snippets)
                        │                 ├──▶ SAOS / NSA / UODO / PMI / ...
                        │                 ├──▶ LEGAL-CITE / EUREKA / EU-COMPLIANCE
                        │                 └──▶ source-specific MCP tools
                        └──▶ /legal_sources (per-document Markdown)
                             └── pl_get_document(source=md), ~5000-char pages
```

Every call lands in a JSONL audit log (timestamp, tool, source, parameter hash,
latency - never document content).

## Development

```bash
git clone https://github.com/matematicsolutions/prawo-pl-mcp && cd prawo-pl-mcp
uv sync --extra dev
uv run pytest          # offline tests: registry, dispatch mapping, pagination, drift
uv run prawo-pl-mcp    # stdio server
```

## License

Apache-2.0. Individual connectors carry their own licenses (MIT or Apache-2.0),
their own rate limits and their own terms toward upstream databases - the
aggregator preserves source provenance and stores fetched Markdown files in
the specifically mounted legal source folder; each upstream source's limits
and attribution requirements continue to apply.

## Deployment for grounding-prawo (NAS)

`deploy/grounding-prawo/` runs one wrapper (`mcp-prawo`, Streamable HTTP `/mcp`) in front of the connectors already
deployed as containers: `saos` (local SAOS dump), `nsa` and `ustawy` (codes and statutes with commentary from
`elconcept/grounding-prawo`, `deploy/mcp-ustawy`). The portal `lex` then needs a single server `prawo`
instead of `saos`, `nsa`, `cite` and `isap`.


## Synology deployment state (2026-11-09)

`docker-compose.nas.yml` is a **proposed** replacement for the production
Portainer stack 58, not an indication that the stack has been redeployed.
Both EUREKA (stack 64) and EU-COMPLIANCE (stack 65) are separately deployed.
The legacy ISAP service and PostgreSQL stack must remain untouched until
separate, explicit retirement approval. The wrapper deliberately does not
connect to or delete their data.

Before any production switch: prepare and verify access to
`/volume1/legal/opracowania/zrodla_prawne_mcp` under user `1029:100`,
without changing the ownership of the entire legal repository; perform live
`tools/list` and `tools/call` against the internal MCP endpoints; verify
the Repertorium default-text compatibility and JSON contract; test cold
LEGAL-CITE and multiple authentic full-text results; run offline regression
tests and a real end-to-end Markdown write/page-read test. Do not disable
Cloudflare Access to work around any public gateway failure.

See `_PLAN/20261109_plan_wykonawczy_mcp_prawo_pmi_eureka_eu_compliance.md`
on the audit branch for the full deployment sequence.
