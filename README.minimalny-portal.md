# Minimalny portal prawny: REPERTORIUM + resolver LOCAL-FIRST

Docelowo model widzi **tylko dwa narzędzia**:
- istniejący `szukaj_repertorium`, pozostawiony bez zmian;
- nowy `pobierz_dokument(identyfikator, artykul?, strona?, sygnatura?, adres_zrodlowy?)`.

Pozostałe MCP (USTAWY, SAOS, NSA, EU-SPARQL, Webwright) nadal działają jako prywatne źródła wewnętrzne. Nie wystawiać narzędzi Webwright bezpośrednio w portalu lex.

## Najpierw lokalnie

| Rodzaj | Lokalna ścieżka | Fallback i zapis |
|---|---|---|
| `eli:DU/2024/917` | istniejące USTAWY SQLite lub wewnętrzne `akt_po_eli` ([PR #81 grounding-prawo](https://github.com/elconcept/grounding-prawo/pull/81)) | dopiero brak lokalny → ELI API; kompletna reprezentacja HTML zapisywana do osobnego SQLite z SHA-256 |
| `saos:166511` | cache fragmentów → SAOS MCP z własnym mirrorem | źródłowe API SAOS obsługiwane w istniejącym serwerze; fragmenty z metadanymi zapisywane w resolverze |
| `nsa:389F2C5B67` | cache fragmentów → NSA MCP | wywołanie CBOSA przez NSA, zapis tylko zweryfikowanych fragmentów |
| `celex:32016R0679:pl` / `RODO art. 33` | lokalny urzędowy korpus PL → lokalny cache PL | wewnętrzny MCP Webwright pobiera kandydat i oficjalny PDF PL; przy poprawnej tożsamości CELEX, ekstrakcji wszystkich stron i SHA-256 zapisuje zweryfikowany tekst oraz oryginalny PDF lokalnie; w przeciwnym razie pozostawia tylko kandydata |
| `ecli:EU:C:2020:559` | lokalny cache urzędowego orzeczenia PL | EU-SPARQL jako fallback metadanych; zapis do `candidates`, nie do pełnego korpusu |
| `sn:...` z `sygnatura` | lokalny cache artefaktów | wewnętrzny Webwright SN; próbuje pobrać pełny oficjalny PDF, weryfikuje sygnaturę i zapisuje tekst+oryginał z SHA-256; jeśli brak tekstu lub PDF, zwraca wyłącznie kandydata |
| MS / TK | dopiero po dodaniu adapterów | obecny ZIP autora nie zawiera skryptów MS/TK; żadnego udawania obsługi |

**Ważne:** bazą USTAWY jest 37 indeksowanych aktów, a nie pełne archiwum Dziennika Ustaw. USTAWY trzymają teksty artykułów; komplet załączników/nowelizacji wymaga odrębnej kontroli. Istniejący angielski EU-COMPLIANCE nie zastępuje polskich tekstów CELEX.

## Staging — bez ingerencji w produkcję

Nowe pliki:
- `src/prawo_pl_mcp/slim_resolver.py` — jedno publiczne narzędzie.
- `src/prawo_pl_mcp/local_corpus.py` — read-only lokalna baza USTAWY i trwały SQLite resolvera, SHA-256.
- `src/prawo_pl_mcp/webwright_internal.py` i `pdf_ingest.py` — dwa wewnętrzne narzędzia Playwright i walidowany import oficjalnych PDF, niewidoczne dla modelu.
- `vendor/webwright_legal_pl` — oryginalne skrypty autora z Apache-2.0.
- `deploy/minimal-legal/compose.staging.yaml` — **dwa kontenery**, resolver i Webwright, osobna sieć, trwały cache.

```bash
# Tylko staging, po przygotowaniu konfiguracji sieci:
docker compose -f deploy/minimal-legal/compose.staging.yaml build
docker compose -f deploy/minimal-legal/compose.staging.yaml up -d
```

Resolver: `127.0.0.1:8414/mcp` na hoście NAS **tylko w staging**. Webwright nie ma mapowania portów hosta. Przed wdrożeniem konieczne: testy dostępu do istniejących upstreamów po LAN, poprawności przeglądarek, rozdzielenia uprawnień i aktualizacji cache. Nie uruchamiać tych komend jako elementu niekontrolowanego auto-deploy.

Zmienna `PRAWO_RESOLVER_CACHE=/data/prawo-resolver.sqlite` trwała przez restarty. `PRAWO_EU_PL_SQLITE=/data/eu-pl.sqlite` jest opcjonalnym zbiorem **uprzednio zweryfikowanych** polskich dokumentów. USTAWY są pobierane przez istniejący MCP po wdrożeniu PR #81, bez potrzeby eksportowania SQLite; opcjonalnie `PRAWO_USTAWY_SQLITE=/ścieżka/tylko-do-odczytu` pozwala na lokalny mount.

## Stan weryfikacji

Przeszły testy kodu SQLite na danych tymczasowych oraz odczytu ELI. Nie przeprowadzono pełnego pytest, build/staging browser ani końcowego testu przez Cloudflare. Walidator PDF ma osobne testy offline z kontrolowanymi danymi, lecz wymaga sprawdzenia z realnymi serwisami. Nie zmieniono konfiguracji portalu lex, żadnego z uruchomionych kontenerów ani REPERTORIUM.

Szczegółowe wyniki i ryzyka: `_PLAN/20261031_repertorium_plus_pobierz_dokument.md`.
