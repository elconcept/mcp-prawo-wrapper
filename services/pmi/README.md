# pmi

Personal, independent public-HTML connector for https://prawmi.pl.

No paid PrawMi API or key. No Tor modifications. Runs inside Portainer
as a separate FastMCP Streamable HTTP server; the existing wrapper accesses
it over the cf_mcp_krs Docker network.

## Native tools

- pmi_search(query, limit=10, kind="auto"): search the entire /ustawa
  title index, or validate a known ruling signature in /orzeczenie/.
  This is not semantic judgment search; free Repertorium provides that.
- pmi_get_document(document_id): full text for
  ruling:xii-ko-26-23, act:kodeks-postepowania-karnego,
  article:ochronie-zdrowia-psychicznego:art-23.
- pmi_get_article(act_slug, article): retrieve single article.
- pmi_list_acts(query="", limit=100): list index, cached 1 hour.

The wrapper continues to expose five public unified tools. The pmi
source uses PRAWO_PL_MCP_URL_PMI=http://pmi:8000/mcp;
pl_search(source="pmi") and pl_get_document(source="auto",
document_id="pmi:article:...") act as ordinary wrapper calls.

Full text goes into existing PostgreSQL on first retrieval;
the wrapper paginates text (~5000 characters per page).
The public acts index itself is not bulk-imported into PostgreSQL.

## Source parsing

Ruling: section#section-tresc .ruling-content (checking H1 signature).
Article: article#przepis div.mt-6.space-y-5 (excluding AI explanation).
Full law: main article[id^="art-"] (articles retain their labels).
Index: direct /ustawa/<slug> anchors (currently 895 entries).

Run self-contained parser tests:

    python -m unittest -q test_server.py

Portainer stack: pmi, separate from mcp-prawo-wrapper.
