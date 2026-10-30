# Audyt cherry-pick: matematicsolutions/prawo-pl-mcp → elconcept/mcp-prawo-wrapper

Data: 2026-10-31. Decyzja: **nie wykonywać mechanicznego cherry-pick całego upstreamu**. Przenosić tylko brakujące, przetestowane zmiany. Dokument powstał po porównaniu zawartości obu repozytoriów, a nie na podstawie README.

## Status i prawa autorskie

Źródło: https://github.com/matematicsolutions/prawo-pl-mcp, licencja **Apache-2.0**, wersja pakietu w upstream `0.2.4`. Lokalny wrapper `elconcept/mcp-prawo-wrapper` zawiera ten sam rdzeń. Przy kopiowaniu nowego kodu Apache-2.0 zachować oznaczenia licencji i wymaganą atrybucję/NOTICE (jeśli wystąpi); nie zakładać, że licencja obejmuje dane prawne baz źródłowych.

### Porównanie plików Git SHA (stan odczytu)

| Plik | Stan | Decyzja |
|---|---|---|
| `src/prawo_pl_mcp/server.py` | SHA identyczny `181fca55f5cdc0d4852dbd399270c8e7bb93e3fc` | Nie kopiować |
| `src/prawo_pl_mcp/pagination.py` | SHA identyczny `75c5fa3dacbba0e41845b34c3986e86bf55b2c51` | Nie kopiować |
| `src/prawo_pl_mcp/audit.py` | SHA identyczny `b3c6069340a7a7f6445fe154f62399f402d2338b` | Nie kopiować |
| `src/prawo_pl_mcp/coverage.py` | SHA identyczny `f87ae152b4eb14b498b18f65a2b18603dc099931` | Nie kopiować |
| `src/prawo_pl_mcp/pool.py` | Elconcept ma dodatkowe `PRAWO_PL_MCP_URL_<ID>` i `StreamableHttpTransport` | Zachować lokalne rozszerzenie |
| `src/prawo_pl_mcp/registry.py` | Elconcept dodaje USTAWY i filtr `PRAWO_PL_MCP_SOURCES`, za to nie rejestruje upstreamowej EUREKA | Zachować lokalną konfigurację, nie nadpisywać; utratę EUREKA odnotować osobno, **nie** przywracać bez decyzji |
| `instructions.py` i schematy narzędzi | Wiele angielskich opisów | Docelowo przetłumaczyć na polski; nie kopiować bez zmian |

W upstream i elconcept jest **pięć**, nie cztery narzędzia: `pl_list_sources`, `pl_search`, `pl_get_document`, `pl_call`, `pl_coverage`. Starszy nagłówek `server.py` błędnie mówi o czterech.

## P0: najważniejszy problem — fałszywa kompletność orzeczeń

`pl_get_document` wywoływał `POOL.call` i ponownie ciął zwrócone `content` na strony po około 5000 znaków. Tymczasem `mcp-saos:get_judgment` zwraca domyślnie tylko pierwsze 2000 znaków; przygotowany PR NSA także stosuje natywne `offset/limit`. Zwrot `has_more=false` po pierwszej stronie agregatora **nie oznacza** końca orzeczenia w źródle.

Implementacja na osobnej gałęzi `fix/upstream-native-pagination-20261031`:
1. `POOL.call_with_metadata` zachowuje zarówno tekst, jak i `structured_content`, bez zmiany historycznej metody `call()` i jej kontraktu.
2. `pl_get_document` dla SAOS/NSA wysyła `offset=(page-1)*5000` i `limit=5000`; wynik zawiera natywne `totalLength`, `hasMore`, `nextOffset` i `citations`, bez ponownego cięcia fragmentu.
3. Jeśli starszy backend nie zwróci metadanych długości, wrapper jawnie raportuje `pagination=unverified` i `has_more=null`, zamiast fałszywego `has_more=false`.
4. Testy offline: SAOS, NSA nowy/stary, cytowania, błąd upstream i brak regresji dla KRS/ISAP.

**Status:** przygotowany roboczy PR; nie wdrożono na NAS. Przed merge uruchomić CI oraz test end-to-end z działającym SAOS/NSA.

## P0: niezależny problem — utrata `structuredContent` w `pl_call`

Kod upstream **i lokalny** w `pool.py::call()` zwraca sam tekst, ignorując `structured_content`, jeśli blok tekstowy istnieje. Jest to mechanizm odrębny od problemu Code Mode portalu `lex`. Nowe `call_with_metadata` udostępnia strukturę wewnątrz wrappera i w `pl_get_document`, ale **nie** zmienia jeszcze kontraktu `pl_call`.

Dalsza naprawa: zaprojektować świadomie wersjonowany tryb `pl_call` zachowujący oryginalne `content`, `structuredContent`, `isError` (bez podwójnego obciążenia kontekstu w domyślnym trybie). Testować z prawdziwym klientem FastMCP i `lex`; nie rozszerzać publicznego schematu bez aktualizacji locka descriptorów i testów kompatybilności.

## P1: jeden MCP europejski a registry agregatora

W elconcept trwają osobne prace nad scaleniem EU-COMPLIANCE i EU-SPARQL do **jednego** MCP z 10 natywnymi narzędziami. `prawo-pl-mcp` ma jeszcze dwie pozycje `eu-sparql` i `eu-compliance`.

Nie usuwać tych pozycji, dopóki nowy kontener nie przeszedł PL corpus + smoke i nie ma poprawnie wystawionego narzędzia `tools/list` na `lex`. Następnie:
- Kierować obie **historyczne nazwy źródeł** do jednego URL tylko w okresie przejściowym, zachowując nazwy narzędzi i dokumentując alias. Docelowo jedna pozycja `eu` z 10 narzędziami.
- Nie tworzyć dodatkowej autoryzacji per upstream; zachować istniejące polityki portalu.
- Dodać polskie opisy, ustawić `POL`/PL bez selektora `lang`. Polski urzędowy korpus 14 aktów pozostaje wymaganym, osobnym zadaniem.
- Nie uruchamiać automatycznego `npx -y` jako niekontrolowanej aktualizacji produkcji; na NAS preferować wersjonowane obrazy i jawny URL kontenera.

## P1: kontrola jakości i bezpieczeństwo

- Język: `instructions.py`, opis `coverage.py`, błędy i metadane katalogu w oryginale są po angielsku. Docelowy **polski-only**, bez zmiany sygnatur/identyfikatorów technicznych.
- `pl_coverage` ma status `ok` i ogólne zdanie o źródłach live; nie zastępuje osobnych raportów pokrycia/aktualności SAOS, NSA, USTAWY ani lokalnego EU snapshotu.
- `PRAWO_PL_MCP_SOURCES=saos,nsa,ustawy` w istniejącym compose wyklucza EU z tego wdrożenia. Nie zakładać, że wrapper jest obecnie produkcyjną ścieżką portalu `lex`; najpierw zbadać właściwe mapowanie Cloudflare.
- Audyt JSONL jest już identyczny z upstream i nie przechowuje treści dokumentów. Chronić hash parametrów i tajne dane; nie rozbudowywać logów o pełne odpowiedzi.

## Kryteria odbioru przed produkcją

1. Żaden dokument SAOS/NSA nie jest oznaczony jako kompletny po zwróceniu jedynie domyślnego chunku. Rozmiar i `has_more` zgodne z backendem; ostatnia strona kończy się poprawnie; brak nakładania fragmentów.
2. Cytowania z `structuredContent` są dostępne w wyniku wrappera; po podłączeniu do portalu `lex` sprawdzona zgodność z natywnym JSON-RPC.
3. Testy bez sieci przechodzą wraz z descriptor lockiem. Osobno testy smoke ze staging na NAS.
4. REPERTORIUM: **wyłączone z zakresu, nie modyfikować kodu, konfiguracji, routingu ani kontenera**.

## Zalecenie architektoniczne

Pożyczamy **wzorce**: zunifikowane parametry, nieukrywanie braków danych, paginację natywną i rejestrowanie metadanych — ale nie przenosimy tych samych plików drugi raz. Ze względu na mieszane technologie i potrzebę separacji awarii agregator Python może pozostać cienkim routerem; samą konsolidację EU-COMPLIANCE+SPARQL można utrzymać jako jedną usługę Node.js z dwiema niezależnymi warstwami danych.
