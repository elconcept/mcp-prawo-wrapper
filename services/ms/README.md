# MS official judgments MCP

Independent HTTP MCP that resolves **exact** `ms:` document IDs from
`apiorzeczenia.wroclaw.sa.gov.pl/ncourt-api/judgement/{details,content}`.
The official XML endpoints return complete judgments without a browser,
so Playwright is not needed on this path.

Native tool: `ms_get_document(document_id)`, accepting either
`ms:151020250000503_I_C_000270_2015_Uz_2016-04-07_001` or the bare ID.

The resolver checks the API-returned full identifier and the signature
in both the metadata and document text. It fails closed on mismatches,
partial page ranges, non-XML responses, and malformed documents. It does
not guess documents by signatures; identical case signatures can belong
to unrelated courts.

Deploy on NAS as separate Portainer stack `mcp-ms`; copy the three runtime files (server.py, asgi.py, Dockerfile) to /volume2/docker/mcp-ms before building. The container
joins the existing `cf_mcp_krs` source network (also used by PMI).
The unified wrapper uses
`PRAWO_PL_MCP_URL_MS=http://mcp-ms:8000/mcp`; register `ms` in
`PRAWO_PL_MCP_SOURCES`. Repertorium results with an `ms:` identifier
hydrate automatically through this MCP. No separate database or
embeddings are created.

Live acceptance document:
`151020250000503_I_C_000270_2015_Uz_2016-04-07_001`
(Sąd Rejonowy w Bytowie, I C 270/15, judgment dated 2016-01-19).
