> **ZASTĄPIONY 2026-11-09:** aktualna dyspozycja przewiduje zwracanie fragmentów Repertorium z nazwami plików Markdown, pobieranie pełnych dokumentów do `elconcept/legal` i odczyt przez `pl_get_document`. Nie wdrażać wariantu zwracającego pełne teksty bezpośrednio w `pl_search`. Aktualny plan: [_PLAN/20261109_repertorium_fragmenty_md_legal_i_legal_cite.md](20261109_repertorium_fragmenty_md_legal_i_legal_cite.md).

# PLAN DECYZYJNY: Repertorium JSON → pełne dokumenty przez MCP, bez lokalnej bazy i embeddingów

**Data:** 2026-11-09  
**Status:** DO AKCEPTACJI. **NIE WDRAŻAĆ BEZ WYRAŹNEJ ZGODY UŻYTKOWNIKA.**  
**Repozytoria:** \`elconcept/mcp-repertorium\`, \`elconcept/mcp-prawo-wrapper\`; punktem odniesienia pozostaje \`matematicsolutions/prawo-pl-mcp\` commit \`6c7bae4\`.  
**Aktualna wersja \`mcp-repertorium\`:** commit \`8f4674cead5509e46e5e516871dbaff12e847516\`.  
**Aktualna wersja wrappera \`main\`:** \`f192d13f2bc5a92f2191740ad744a2e29a17b2ce\`.  

**Zastępuje wcześniejszy kierunek architektoniczny:** `_PLAN/20261108_repertorium_master_vector_db_embeddinggemma2.md` (MASTER DATABASE, pgvector/Qdrant/LanceDB i embeddingi), który jest **NIEAKTUALNY w świetle dyspozycji z 9 listopada 2026 r.** Nie realizować tamtego planu w odniesieniu do wrappera. Niniejszy dokument nie upoważnia do usuwania współdzielonych usług innych projektów.

**Autoryzacja w tej rozmowie:** ustalenie wymagań, analiza wyłącznie w trybie odczytu i zapis planu Markdown. Żadnych zmian kodu, kontenerów, bazy, stacków ani przełączeń portalu.

## 1. Zatwierdzone kierunki funkcjonalne (nie tożsame ze zgodą na wykonanie)

1. \`pl_search(query=...)\` bez parametru \`source\` ma nadal wybierać \`repertorium\`.
2. Jedno narzędzie \`szukaj_repertorium\` uzyska opcjonalny parametr formatu odpowiedzi, domyślnie zachowujący **dokładnie obecną ścieżkę** tekstową. Żadnych zmian w pozostałych klientów ani narzędziach Repertorium poza koniecznym testem kompatybilności.
3. \`format=json\` ma zwracać pełną **strukturę JSON** otrzymaną z konsolowego API, bez przerabiania jej na listę trafień w Markdown i bez usuwania pól. \`format=text\` pozostaje domyślny.
4. Gdy \`pl_search\` używa Repertorium, pod maską prosi o JSON, czyta trafienia i \`document_id\`/źródło, odpytuje właściwy już działający MCP, pobiera dokument źródłowy, paginuje odpowiedź i dołącza jawny sposób żądania następnej strony.
5. Model otrzymuje treść dokumentów, a nie same \`fragment\`/snippety. Jeśli dane źródło lub pełny dokument nie są dostępne, wynik musi jasno deklarować \`unavailable\`/\`partial\`, nie udawać pełnego tekstu.
6. Cache PostgreSQL, lokalny embedder i związane z tą koncepcją ścieżki przetwarzania dokumentów zostają **odrzucone z architektury wrappera**. Nie wprowadzać alternatywnego Qdrant, cache dyskowego, FAISS ani lokalnego embeddingu pod inną nazwą.
7. Natywne \`pl_search(source="saos"/"nsa"/"isap"/...)\` oraz \`pl_call\` mają pozostać zgodne wstecznie. Niezmienione pozostają osobne konektory MCP, ich repozytoria, wdrożenia i dane.

## 2. Stan stwierdzony w źródłach

### Repertorium

W \`elconcept/mcp-repertorium/index.js\` \`szukajRepertorium(q, jurysdykcja)\` wykonuje POST do \`https://matematicsolutions.com/api/repertorium/szukaj\`, \`data: {q, jurysdykcja}\`, otrzymuje \`response.data\`. \`CallToolRequestSchema\` wywołuje następnie \`formatTrafienie()\`, które odczytuje \`dane.trafienia\`, \`tytul\`, \`data\`, \`sad\`, \`document_id\`, \`fragment\`, \`zrodlo_url\`/\`zrodlo\` i zwraca tylko tekst MCP. Jedynym narzędziem jest \`szukaj_repertorium(q, jurysdykcja="pl")\`. Kod operuje przez Tor/SOCKS i ma mechanizm retry; **nie modyfikować tego transportu przy tej zmianie**, chyba że oddzielny plan zostanie zatwierdzony.

Oficjalny interfejs \`matematicsolutions/repertorium\` opisany w dokumentach \`docs/tools.md\` / \`docs/response-contract.md\` to **inny, szerszy interfejs tokenowy** (m.in. \`search_law\`, \`get_document\`, \`citation_locator\`, \`snapshot\`). Nie wolno bez próbki zakładać, że konsolowe API \`/api/repertorium/szukaj\` zwraca identyczne pola. Schemat konsoli można wywodzić tylko z obecnego kodu i późniejszych niezmienionych próbek JSON.

### Wrapper

\`src/prawo_pl_mcp/registry.py\`: \`repertorium\` → narzędzie \`szukaj_repertorium\` i parametr \`q\`.  
\`src/prawo_pl_mcp/server.py\`: \`pl_search(source="repertorium")\` obecnie zwraca tekst otrzymany z \`_proxy_call\` i uruchamia \`_prefetch_repertorium_hits\`; \`pl_get_document\` korzysta z \`local_docs\`, PostgreSQL, dumpu SQLite SAOS i bezpośredniego pobierania PDF ELI.  
\`src/prawo_pl_mcp/pool.py\`: \`POOL.call\` preferuje bloki \`content[].text\`, a dopiero potem \`structured_content\`; jest więc potrzebna **jawna ścieżka odpowiedzi strukturalnej wyłącznie dla nowego trybu**.  
\`docker-compose.nas.yml\`: wrapper łączy się z istniejącymi MCP przez Streamable HTTP, ale posiada też połączenie \`prawo-vector-db\`, sekret DB i mount SAOS SQLite.  
\`pyproject.toml\`: zależności \`psycopg[binary]\`, \`beautifulsoup4\`, \`pypdf\` zostały dodane dla mechanizmu \`local_docs\`.  
\`test_descriptor_lock.py\` + \`tools.lock.json\`: obecnie niezsynchronizowane z domyślnym source=Repertorium; plan musi jawnie uzgodnić wersjonowany kontrakt publiczny.

### Infrastruktura

- Portainer 19: \`mcp-repertorium\`, odrębny stack; jego \`index.js\` jest montowany z hosta \`/volume2/docker/mcp-repertorium/index.js\` jako \`read-only\`.
- Portainer 58: \`mcp-prawo-wrapper\`, działa z istniejącymi MCP.
- Portainer 57: \`prawo-vector-db\`, osobny PostgreSQL/pgvector z bind mountem \`/volume2/docker/prawo-vector-db/data\`. Sieć wewnętrzna \`mcp_prawo_private\` ma obecnie dokładnie dwa kontenery: \`prawo-vector-db\` oraz \`mcp-prawo-wrapper\`.
- Portainer 45: \`shared-embeddings-small\` / \`shared-e5-small\`, jest **współdzielony**, nie jest bezpośrednią zależnością zidentyfikowaną w kodzie wrappera. **Nie usuwać tego serwisu automatycznie.** W repo wrappera nie znaleziono własnego algorytmu generowania embeddingów.
- Usunięcie produkcyjnego PostgreSQL i jego wolumenu wymaga osobnego potwierdzenia braku innych klientów, zachowania kopii bezpieczeństwa zgodnie z dyspozycją i późniejszej akceptacji operacji destrukcyjnej. Odrzucenie architektury cache nie oznacza obecnie zgody na skasowanie fizycznych danych.

## 3. Kontrakt nowego trybu \`szukaj_repertorium\`

**Interfejs MCP:** \`szukaj_repertorium(q: string, jurysdykcja: "pl"|"eu"="pl", format: "text"|"json"="text")\`.

- Domyślny \`format=text\`: pozostawić obecną gałąź \`formatTrafienie\` i budowanie \`content:[{type:"text",text:"..."}]\` bez jakichkolwiek zmian w tekście, kolejności, limitach, statusach i błędach. Obecni klienci nie podają parametru \`format\` i otrzymują to samo co dziś.
- Nowy \`format=json\`: do \`structuredContent\` przekazać obiekt JSON z \`response.data\` bez przekształcania/usuwania pól. Dla interoperacyjności z klientami rozumiejącymi tylko bloki tekstowe można równolegle przekazać \`content[].text\` jako **wierną serializację JSON**, ale nie listę Markdown. Wrapper preferuje obiekt strukturalny, nie sparsowany opis.
- \`response.data\` jest już obiektem powstałym z dekodowania JSON w Axios. To zachowuje **semantykę i pola**, nie gwarantuje identycznych bajtów oryginalnego HTTP (whitespace, kolejność znaków). Gdyby wymaganiem było literalne porównanie bajt po bajcie, trzeba przewidzieć \`responseType:'text'\` w gałęzi JSON i osobny test; bez takiej zgody nie przedstawiać serializacji jako bajtowej kopii.
- Nie zmieniać żądania do API, parametrów \`q,jurysdykcja\`, proxy Tor, retry, istniejącego formatu \`text\`, ani pozostałych narzędzi.
- Nowy opcjonalny parametr zmienia schemat \`tools/list\`, więc należy utrwalić test kontraktowy i wydać świadomą wersję konektora, choć dotychczasowe wywołania zachowują znaczenie.

## 4. Algorytm \`pl_search\` w trybie Repertorium

1. Przy braku \`source\`: \`repertorium\`. Przy jawnie innym źródle: **dotychczasowy mechanizm unified bez hydracji**.
2. W trybie \`repertorium\` wysłać do istniejącego MCP \`szukaj_repertorium\` z \`format=json\` i jurysdykcją zgodną z żądaniem (\`pl\` domyślnie), bez bezpośredniego wykonywania requestu API przez wrapper.
3. Przyjąć strukturę trafień \`dane.trafienia\` i pola ID dopiero po walidacji przeciw **rzeczywistym**, zanonimizowanym fixture JSON: zapytanie po sygnaturze, przepisie, ogólne semantyczne, pusty wynik, częściowe pokrycie, odpowiedź UE. Dokumentacja osobnego API MateMatic to nie fixture konsolowego endpointu.
4. Każdemu trafieniu przypisać jeden status rozwiązywania źródła, zapamiętać \`document_id\`, oryginalny tytuł, sygnaturę/datę, \`source_url\`, kolejność/relevance oraz źródło. Rozpoznanie identyfikatora musi być deterministyczne, bez dopasowywania „na podobieństwo” i bez podstawiania pierwszego wyszukania jako dokumentu o tej samej tożsamości.
5. Przez tabelę identyfikatorów skierować pobranie do **jednego właściwego MCP** (tabela niżej); uzyskać pełny tekst, jawnie sprawdzić \`isError\`, obecność właściwej treści, zgodność ID/tytułu/sygnatury i ograniczenia kompletności. Weryfikować aktualność publikacji i tekst jednolity odrębnie — wynik semantyczny nie staje się automatycznie aktualnym stanem prawnym.
6. Zwracać w \`pl_search\` **początkowe strony treści** wybranych znalezionych dokumentów z budżetem wyjścia, a nie sam fragment wyszukiwarki. Każdy element musi zawierać \`document_id\`, \`source\`, \`title\`, \`source_url\`, \`fetched_from_mcp\`, \`retrieval_status\`, \`page\`, \`total_pages/has_more\` jeśli prawdziwe, \`total_chars\` jeśli znane, \`content\` oraz konkretny następny call \`pl_get_document(source="auto",document_id="...",page=N)\`. Dla serwisów z natywną paginacją respektować ich własne numery stron.
7. Nie tworzyć cache trwałego ani prefetch do PostgreSQL. Dopuszczalne tylko niezbędne obiekty w RAM podczas trwania konkretnego zapytania; kolejne strony pobierać ponownie z właściwego MCP. Zmianę wersji tekstu między wywołaniami sygnalizować tam, gdzie źródło udostępnia identyfikator wersji i datę.
8. Nie ukrywać niepełnego źródła: przy niedostępnym pełnym tekście zwrócić \`retrieval_status:"unavailable"/"partial"\`, powód i ewentualnie oryginalny fragment **wyraźnie jako fallback**, nigdy jako pozornie kompletny dokument. Błąd źródła nie może wyzerować wyników innych źródeł.

**Paginacja/budżet:** projektowany default: maksymalnie 5 trafień z pełnym pobraniem na stronę wyników, maks. 3500–4000 znaków pierwszej strony na dokument, ograniczenie całej odpowiedzi ok. 20–25 tys. znaków. To **parametry planu do zatwierdzenia i dostrojenia testem**, nie wdrożone wartości. \`pl_search.page\` oznacza stronę **listy trafień** (dotąd Repertorium nie posiadało mapowania page), \`pl_get_document.page\` oznacza stronę **tekstu dokumentu**. Wyniki w obu przypadkach wymagają jasnego metadanych i gotowego sposobu przejścia. Przy odświeżonym wyszukiwaniu kolejność trafień może się zmienić — brak trwałego snapshotu wymaga jawnej informacji.

## 5. Macierz źródeł i granice rekonstrukcji

| Identyfikator Repertorium | Preferowany resolver | Zakres do testów i ograniczenia |
|---|---|---|
| \`saos:<ID>\` | \`mcp-saos\` → \`get_judgment(id)\` | Natywne ID, pełny tekst; nie zastępować automatycznie przypadkowym SAOS po podobnej sygnaturze |
| \`nsa:<HEX>\` | \`mcp-nsa\` → \`get_judgment(doc_id)\` | Wymaga rzeczywistego hex/doc_id i sprawdzenia identyczności |
| \`kio:<ID>\` | \`mcp-kio\` → \`kio_get_orzeczenie\` | Ustalić czy ID źródła to numeryczny klucz czy sygnatura |
| \`uodo:<URN>\` | \`mcp-uodo\` → \`uodo_search_decisions\` → \`uodo_get_decision\` | Wyszukać PublicDocument ID; **zweryfikować zgodność sygnatury** w trafieniu, nie wybierać pierwszego bez kontroli |
| \`eli:DU/YEAR/POS\` | \`mcp-isap\` → \`get_act_text\`; opcjonalnie \`mcp-ustawy\` dla wskazanego artykułu po jednoznacznej identyfikacji | Nie mieszać wersji pierwotnej/jednolitej i zmian w czasie; przekazać \`search_text\` tylko po sprawdzeniu parametru MCP |
| \`sn:<ID>\` | Do rozpoznania | SN jest w Repertorium, ale osobny działający resolver \`sn\` nie został wykazany; SAOS tylko gdy identyczność dokumentu udokumentowana |
| \`eureka:<ID>\` | Do rozpoznania | EUREKA usunięto z aktywnego registry po PR #2; nie udawać, że źródło jest dostępne |
| \`celex:<CELEX>:<lang>\` | \`mcp-eu-sparql\` i ewentualnie zaakceptowane źródło UE | \`search_by_celex\` może dostarczyć metadane, a nie pełny tekst; nie oznaczać „complete”, gdy to tylko tytuł/URL |
| inne/nieznane | brak automatycznego zgadywania | Jawny status i oryginalny \`document_id\`; bez fałszywego „pełny tekst” |

Priorytet resolverów to zgodność tożsamości i wersji, nie preferencja do dowolnego osiągalnego serwera. W niejednoznacznym przypadku zwrócić problem, nie wymyślać mostka.

## 6. Usunięcie lokalnej warstwy magazynowania z wrappera

**Do usunięcia po akceptacji implementacji:**
- Moduł \`src/prawo_pl_mcp/local_docs.py\` jako repozytorium cache/SQLite/PDF; z zachowaniem jedynie **czysto funkcjonalnego, bezstanowego** parsera identyfikatorów w osobnym module resolvera.
- Importy/ścieżki \`read_cached\`, \`save_cached\`, \`read_saos_dump\`, \`read_eli_pdf\`, \`_prefetch_repertorium_hits\`, automatyczny background write; \`psycopg[binary]\`, \`beautifulsoup4\` i \`pypdf\` wyłącznie jeśli okażą się zbędne dla pozostałych ścieżek.
- \`PRAWO_DB_HOST/NAME/USER/PASSWORD_FILE\`, mount sekretu DB, mount \`/saos\` **we wrapperze** i sieć \`mcp_prawo_private\` jeśli pozostanie niepotrzebna po usunięciu cache.
- Używanie \`prawo-vector-db\` z poziomu agregatora. Nie zastępować inną trwałą lokalną bazą ani embeddingiem.

**Osobny etap destrukcyjny, nieautoryzowany tym dokumentem:** po wykazaniu braku innych klientów i kontroli danych dedykowanej bazy, dopiero po zgodzie użytkownika zatrzymać/wycofać stack Portainer 57 \`prawo-vector-db\`, a później usunąć dedykowane bind mounty /volume2/docker/prawo-vector-db/data i konfigurację, zgodnie z zatwierdzoną polityką archiwizacji/usunięcia. Samo odrzucenie rozwiązania NIE oznacza zgody na natychmiastowe skasowanie danych. **Nie usuwać współdzielonego \`shared-e5-small\` (stack 45)** bez osobnego audytu własności.

## 7. Testy wymagane przed uruchomieniem zmian

### Repertorium — gwarancja pełnej zgodności dotychczasowych klientów
- Złote fixture: \`szukaj_repertorium(q)\`, \`szukaj_repertorium(q,jurysdykcja="pl")\` i \`jurysdykcja="eu"\` zwracają dokładnie dawny \`content\` w trybie domyślnym; identyczne komunikaty błędów.
- Nowe \`format=json\` zachowuje wszystkie klucze, typy, ID i wartość pól przykładowego \`response.data\`. Równoważność porównaniem obiektu, bez wycieku danych.
- \`format\` spoza enum → jawny \`invalid_arg\`; zachowany \`isError\`; \`tools/list\` zawiera jedynie dodany parametr opcjonalny.
- Test bez zmian w proxy Tor, jurysdykcji, endpointach, retry i pozostałych kontenerach.

### Wrapper — orkiestrowanie i odporność
- Golden fixtures po jednym dla SAOS, NSA, KIO, UODO, ELI, po stronie UE i przypadki SN/EUREKA nieobsługiwane.
- Porównać hash tekstu natywnego MCP i treści rekonstruowanej ze wszystkich stron, nie tylko pierwszej.
- Dokument z 1, 2, 20 i >100 stron; wyszukiwanie zwracające 0, 1, 5 i >5 dokumentów; puste/fatal/partial/timeout; niedostępne MCP; nieprawidłowe ID; utrata \`structuredContent\`.
- \`pl_search(source="nsa"/"saos"/"isap")\` — zachowanie upstream, bez nowego fan-out. \`pl_call\` — zgodność z dotychczasowym narzędziem.
- \`pl_get_document(source="auto",document_id=...,page=n)\` — bez PostgreSQL, bez lokalnych zapisów, z natywną lub bezstanową paginacją i poprawnymi sygnaturami.
- \`pl_coverage\`, \`INSTRUCTIONS\`, README i \`tools.lock.json\` uaktualnione tak, by nie obiecywały nieistniejącego cache lub automatycznej federacji wszystkich baz.
- Kontrola kosztu i przepływu: maksymalna długość odpowiedzi, timeout i limit równoległych połączeń per-source, brak nieskończonego oczekiwania i brak floodu.
- Testy nie powinny używać prawdziwych wrażliwych dokumentów spraw; stosować publiczne fixture i metadane.

### Wdrożenie
- Etap testowy, bez podmiany produkcyjnego \`index.js\` czy stacka. Proponowane PR osobno dla \`mcp-repertorium\` i \`mcp-prawo-wrapper\`.
- Test \`initialize\`/ \`tools/list\`/ \`pl_search\`/ \`pl_get_document\` bezpośrednio przez MCP HTTP oraz przez Cloudflare/Lex. Wcześniej udokumentowany problem \`mcp-prawo\` w Cloudflare (\`text/html\` podczas negocjacji) trzeba wyeliminować osobnym zaakceptowanym krokiem; healthy kontenera tego nie dowodzi.
- Bez ograniczania bezpieczeństwa Cloudflare Access, bez zmiany poświadczeń, bez zmian produkcyjnych do zaakceptowanego okna.
- PR, wyniki CI, zaakceptowana lista ścieżek i osobne **zatwierdzenie produkcyjnego wdrożenia**, potem realizacja.

## 8. Decyzje zamknięte i wciąż otwarte

**Zamknięte przez dyspozycję użytkownika:**
- D03: \`pl_search\` domyślnie Repertorium, z transparentnym pobieraniem tekstów.
- D05: bez PostgreSQL/cache/embeddingów w wrapperze; docelowo usunięcie dedykowanej infrastruktury po zabezpieczeniu i akceptacji destrukcyjnego etapu.
- Format Repertorium: \`text\` default, \`json\` na żądanie.
- Model musi dostawać stronicowane pełne teksty i instrukcję pobierania dalszych stron.

**Do decyzji wraz z akceptacją szczegółowego planu:**
- Dokładny limit trafień i znaków na wywołanie \`pl_search\` (propozycja 5 × 4000, 20–25 tys. znaków).
- Zachowanie przy brakującym resolverze SN/EUREKA/UE: jawny status i wskazanie oryginalnego fragmentu jako fallback, bez symulowania sukcesu (bezpieczna wartość domyślna).
- Czy dodatkowo zestawić dokładny plan późniejszego, destrukcyjnego usunięcia stacka 57 i jego danych, po zakończeniu wdrożenia stateless.

## 9. Bramka akceptacji

**Ten plik stanowi plan, nie upoważnienie do działania.** Bez osobnej i jednoznacznej akceptacji: nie zmieniać \`index.js\`, wrappera, \`main\`, konfiguracji/Portainer/Cloudflare, sekretów ani PostgreSQL; nie uruchamiać migracji i rollbacku. W razie wykrycia nowych wymagań poza planem — sporządzić jego rewizję Markdown do kolejnej akceptacji.