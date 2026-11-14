# Synology — MCP Prawo (main, 0.3.0)

Jedyny katalog produkcyjny: `/volume2/docker/mcp-prawo`.

Portainer: stack 58 (`/volume2/docker/portainer/compose/58/docker-compose.yml`).
Używa `docker-compose.nas.yml` z repozytorium i buduje `mcp-prawo:0.3.0`.
Kontener: `mcp-prawo`, port HTTP 8000, diagnostyka na `127.0.0.1:8420`.
Cloudflare Tunnel ds1821: sieć `cf_mcp_prawo`, usługa `http://mcp-prawo:8000`, host `mcp-prawo.xlap.pl`, ścieżka `/mcp`.

## Architektura

Gateway Streamable HTTP FastMCP agreguje Repertorium, SAOS, NSA, MS, LEGAL-CITE, KRS, KIO, UODO, PMI, EU-SPARQL, EUREKA i EU-COMPLIANCE (wg `PRAWO_PL_MCP_SOURCES`).
Pięć narzędzi: `pl_coverage`, `pl_list_sources`, `pl_search`, `pl_get_document`, `pl_call`.
`pl_search` wyszukuje wyniki Repertorium i równolegle próbuje pobrać pełną treść z odpowiedniego oficjalnego źródła. Zachowuje rozróżnienie `full`, `article_only`, `fragment_only`.
Wyniki zapisuje jako pliki Markdown w `/volume1/legal/opracowania/zrodla_prawne_mcp`, zamontowane pod `/legal_sources`. `pl_get_document(source="md")` czyta plik stronami i weryfikuje SHA-256. Brak PostgreSQL, pgvector, prywatnego SQLite i własnych embeddingów.

## Zasady aktualizacji

Praca tylko na `main` — bez gałęzi roboczych i worktree. Każdą zmianę należy zatwierdzić i wypchnąć. Przed wdrożeniem: `pytest` i `ruff` oraz test integracyjny MCP. Nie publikować sekretów, nie modyfikować kontenerów źródłowych ani rotatora Repertorium.
Po zmianie Compose aktualizować również plik stacka 58 i odtworzyć kontener `docker compose up -d --build --force-recreate mcp-prawo` w tym projekcie.
Dostęp zewnętrzny chroni Cloudflare Access; autoryzację konfiguruje się w Cloudflare, nie poprzez osadzanie sekretów w repozytorium.

## Diagnostyka

`docker inspect mcp-prawo` — status i sieci.
`docker logs mcp-prawo` — błędy wykonania.
Wywołać protokół MCP `initialize`, `tools/list`, a następnie `pl_search` / `pl_get_document` zarówno lokalnie, jak i przez publiczny host.
