# Minimalny portal prawny — dwa narzędzia

Połącz w portalu `lex` **dwa osobne serwery MCP** (nie dwa serwery z 40 narzędziami):

1. Istniejący **REPERTORIUM** (bez zmian): `szukaj_repertorium(q, jurysdykcja)`.
2. Nowy **resolver dokumentów**: tylko `pobierz_dokument(identyfikator, artykul?, strona?, adres_zrodlowy?)`.

Nie rejestruj w tym portalu pozostałych źródeł (SAOS, NSA, KRS, BASIC-MEMORY itd.) jako narzędzi bezpośrednio dostępnych modelowi. Ich kontenery mogą pozostać jako wewnętrzne backendy lub w portalu `ai`.

## Uruchomienie testowe bez zmian REPERTORIUM

Wymagane: Python >=3.11, zależności repo i dostępność SAOS/NSA przez istniejący mechanizm `PRAWO_PL_MCP_URL_...`.

- Stdio: `pobierz-dokument-mcp` (po instalacji `pip install -e .`).
- HTTP: `uvicorn prawo_pl_mcp.slim_asgi:app --host 0.0.0.0 --port 8000`.
- Test offline: `pytest -q tests/test_slim_resolver.py tests/test_pool_metadata.py`.

Do testów integracyjnych:
```bash
PRAWO_PL_MCP_SOURCES=saos,nsa,ustawy
PRAWO_PL_MCP_URL_SAOS=http://10.0.10.201:8402/mcp
PRAWO_PL_MCP_URL_NSA=http://10.0.10.201:8405/mcp
```
Są to **przykłady ustawień testowych dla znanej sieci NAS**, nie nowa konfiguracja produkcyjna. Zachowaj istniejący Cloudflare Access. W modelu wystaw wyłącznie jeden resolver z tego serwera.

## Status obsługi

- `eli:DU/2024/917` i `Dz.U. 2024 poz. 917`: pobranie metadanych Sejmu i tekstu HTML, stronicowanie; jawna data stanu prawnego oraz nowelizacje wymienione w metadanych.
- `nsa:389F2C5B67`, `saos:166511`: delegowanie do źródłowego `get_judgment` z `offset/limit`; w wynikach zachowuje `totalLength`, `hasMore`, `nextOffset`, cytowania. Stary NSA bez metadanych → **niezweryfikowana kompletność**, nie fałszywe `has_more=false`.
- `celex:32016R0679:pl` i `RODO art. 33`: obecnie oficjalny link PL, **jeszcze bez pełnego tekstu** — pozyskanie urzędowego polskiego CELEX pozostaje P0.
- `sn:...`, `edpb:...:pl`, `ms:...`, `eureka:...`, `ecli:...`: bezpieczny link źródłowy i jawne `tylko_link`; pełny odczyt wymaga odrębnej weryfikacji adaptera.
- Nieobsługiwany format → `nieobsługiwany_id`; bez automatycznego zgadywania lub zapytania do wszystkich baz.

**Nie wdrażać jako kompletnego serwisu przed testami z żywymi backendami i potwierdzeniem jakości pełnych tekstów.** Testy parsera/stronicowania nie zastępują integracji.

## Ograniczenia

Resolver wykorzystuje istniejący `mcp-prawo-wrapper` jako bibliotekę pomocniczą, lecz ma własny obiekt `FastMCP` i własne `tools/list` liczące **jedno narzędzie**. Nie wymaga migracji bazy ani modyfikacji REPERTORIUM. Nie tworzyć dedykowanych polityk per źródło — autoryzacja pozostaje w portalu.
