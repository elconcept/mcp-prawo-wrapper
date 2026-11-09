# PLAN DO AKCEPTACJI — pl_search: fragmenty Repertorium + pełne dokumenty Markdown w legal

Data: 2026-11-09  
Status: **NIEZATWIERDZONY — WYŁĄCZNIE AUDYT I PLAN.** Żadnych zmian kodu, konfiguracji, kontenerów, plików repozytorium legal, uprawnień, sieci, bazy ani usuwania zasobów bez wyraźnej akceptacji.

Repozytoria: elconcept/mcp-repertorium, elconcept/mcp-prawo-wrapper, elconcept/legal. Upstream referencyjny: matematicsolutions/prawo-pl-mcp (commit 6c7bae4).  
Ten plan zastępuje wcześniejszą koncepcję zwracania pełnych treści bezpośrednio przez \`pl_search\` w \`_PLAN/20261109_pl_search_repertorium_json_fulltext_bez_cache.md\`. Nowa architektura **zwraca modelowi oryginalne fragmenty i ścieżki do osobnych plików Markdown**, a nie wielkie teksty w odpowiedzi wyszukiwania. Nie wprowadza PostgreSQL, lokalnego embeddera ani własnej wyszukiwarki.

## 1. Dyspozycje użytkownika — nie zmieniać założeń

1. \`pl_search\` bez \`source\` domyślnie kieruje wyszukiwanie semantyczne do istniejącego \`mcp-repertorium\`.
2. W \`szukaj_repertorium\` dodać **wyłącznie opcjonalny parametr** \`format=text|json\`, domyślnie \`text\`. Obecne \`content\`, komunikaty, kolejność i zachowanie standardowych wywołań muszą pozostać identyczne. \`json\` zwraca kompletny obiekt otrzymany w \`response.data\` konsolowego API, bez konwersji na tekst trafień i bez usuwania pól.
3. Wrapper używa \`format=json\` wyłącznie wewnętrznie. Modelowi zwraca **oryginalne fragmenty** wraz z oryginalnymi polami trafień, rozszerzone o identyfikator pliku \`md_file\`, \`fulltext_status\` i informacje o ewentualnym niepowodzeniu.
4. Wrapper przy każdym wyszukiwaniu podejmuje próbę pobrania pełnego tekstu **każdego** trafienia przez właściwy istniejący serwer MCP, po czym zapisuje osobny plik Markdown dla każdego unikatowego dokumentu. Nie zapisuje lokalnych embeddingów, nie stosuje PostgreSQL ani SQLite jako magazynu pełnych tekstów.
5. **Niepowodzenie pobrania pełnego tekstu NIE usuwa trafienia.** Zachować oryginalny fragment i dołączyć niepomijalną, jawną informację, że nie udało się uzyskać pełnej treści. Taka sama informacja musi znaleźć się w metadanych ewentualnego pliku fragmentowego oraz w instrukcji dla modelu: przy przedstawianiu tego trafienia użytkownikowi ma obowiązek powiedzieć, że dysponuje tylko fragmentem.
6. W katalogu projektu \`legal\` mają powstawać pliki \`.md\` z metadanymi YAML frontmatter i deterministycznymi, czytelnymi nazwami.
7. Agent działający na plikach projektu \`legal\` odczytuje je bezpośrednio; klient w trybie Chat korzysta z rozszerzonego \`pl_get_document\`, który odczytuje Markdown i zwraca żądaną stronę, bez zalewania kontekstu.
8. W aktywnym registry wrappera zastąpić źródło \`isap\` integracją \`legal-cite\`, a \`legalize\` zastąpić \`pmi\`. Nie wymyślać nowego serwera dla SN. Żadnych działań wobec osobnych konektorów przed zatwierdzeniem odpowiedniej fazy.
9. Zmiany tylko po osobnej akceptacji planu; wcześniej wolno jedynie badać i zapisać plan Markdown.

**Zakres projektu obejmuje tylko elconcept/mcp-repertorium i zainstalowane już serwery MCP. Nie planować i nie implementować żadnego innego interfejsu Repertorium.**

## 2. Potwierdzone źródła i mapowania

### Upstream mcp-prawo
- \`eureka\` jest mapowane na pakiet \`@matematicsolutions/mcp-eureka\` (\`search\`, \`get_interpretation(id)\`). W obecnym forku EUREKA została zastąpiona \`ustawy\` w październikowym PR.
- W upstream **nie istnieje samodzielne źródło \`sn\`**. Zbiory SAOS obejmują też orzeczenia SN, lecz \`sn:<ID>\` z Repertorium NIE jest z definicji tożsame z \`saos:<ID>\`. Resolver nie może zgadywać.
- \`legalize\` występuje w oryginalnym registry i obecnym forku, natomiast \`pmi\` zostało już dodane do forka. Usunięcie \`legalize\` ma pozostawić \`pmi\` jako docelowe źródło, bez dublowania wpisu.

### Synology/Portainer — odczyt 2026-11-09
| Usługa | Kontener | Status kontenera |
|---|---|---|
| SAOS | mcp-saos | running, healthy |
| NSA | mcp-nsa | running, healthy |
| KRS | mcp-krs | running, healthy |
| KIO | mcp-kio | running, healthy |
| UODO | mcp-uodo | running, healthy |
| EU-SPARQL | mcp-eu-sparql | running, healthy |
| EUREKA | brak mcp-eureka | nie uruchomiona |
| EU-COMPLIANCE | brak mcp-eu-compliance | nie uruchomiona |
| LEGAL-CITE | legal-cite | running, healthy |
| PMI | pmi | running, healthy |
| ISAP (legacy) | mcp-isap | running, healthy — nie usuwać przed decyzją |

Bezpośrednie \`tools/list\` LIVE z \`legal-cite\` potwierdziło \`verify_article(citation,na_dzien?)\` i \`list_acts()\`. Wynik live \`verify_article("art. 415 KC")\` **nie został potwierdzony** — test przekroczył limit zdalnego wywołania. Kod i README projektu \`apiotrowski-afk/legal-cite-pl\` dokumentują obsługę Dz.U. publikowanych wyłącznie jako PDF przez eli2md + pdftotext, ale jest to **odczyt pojedynczego artykułu lub paragrafu**, nie tekstu całej ustawy. Odczyt z PDF może być opatrzony kwalifikacją nieurzędowego odczytu i oceną wierności, a gdy kontrola zawiedzie, narzędzie może odmówić. Nie obiecywać 100% pokrycia ani nie podawać nieotrzymanego fragmentu jako tekstu pełnego. Wbudowany cache konwersji PDF w LEGAL-CITE to niezależny mechanizm tej usługi; nie jest cache wrappera, który użytkownik nakazał usunąć.

### Sieci Docker
- Wrapper jest podłączony do \`cf_mcp_saos\`, \`cf_mcp_nsa\`, \`cf_mcp_krs\`, \`cf_mcp_uodo\`, \`cf_mcp_eu_sparql\`, \`cf_mcp_repertorium\`, \`cf_mcp_isap\` i \`mcp_prawo_private\`.
- LEGAL-CITE jest **tylko** w \`cf_mcp_cite\`, do którego wrapper nie jest obecnie podłączony. Konieczna będzie zaakceptowana modyfikacja sieci compose, aby wywołania \`verify_article\` docierały do serwisu.
- KIO i PMI działają w \`cf_mcp_krs\`, już współdzielonej z wrapperem.
- Nie należy mylić \`healthy\` kontenera z poprawną obsługą \`tools/call\` i prawidłowym pełnym tekstem dokumentu.

## 3. Lokalizacja w projekcie legal i prawa dostępu

- Stwierdzono na Synology udział \`/legal\`, zawierający **pełny klon Git** (\`.git\`), \`opracowania\`, \`dowody\`, \`sprawy\`, \`output\` itd.
- Host Docker obecnie montuje ten udział jako \`/volume1/legal\` do \`/workspace/legal\` w kontenerach \`vscode\` i \`Holyclaude\`. Nie wymaga to tworzenia drugiej, niezależnej kopii danych.
- Proponowany nowy katalog wewnątrz repo: \`/volume1/legal/opracowania/zrodla_prawne_mcp/\`.
- Do wrappera zamontować **WYŁĄCZNIE TEN KATALOG** jako bind mount \`/legal_sources:rw\`. Nie montować całego \`legal\` — zawiera prywatne sprawy, sekretne \`.env\` i inne materiały niezwiązane z wyszukiwaniem.
- Katalog \`/volume1/legal/opracowania\` ma obecnie właściciela \`1026:100\` i tryb raportowany \`0700\`; wrapper działa jako \`1029:100\`. Na NAS występują też ACL DSM. Przed wdrożeniem **zweryfikować skuteczne prawa wejścia** (POSIX/ACL) i wykonać wyłącznie najmniejsze uzasadnione dostosowanie. Propozycja dla nowego podkatalogu: właściciel \`1029\`, grupa \`100\`, setgid i \`2770\`, aby pliki były dostępne użytkownikom i agentom z grupy \`users\`; w razie niedostępności nadrzędnych katalogów zastosować jawnie zatwierdzony ACL lub montować bezpośrednio wygenerowany podfolder. **Nie robić chown -R /volume1/legal** i nie rozluźniać uprawnień całego repozytorium.
- Zawartość folderu zostanie utworzona dopiero po zatwierdzeniu; obecna analiza nie wprowadziła żadnych plików do legal.

### Dostępność plików w różnych agentach

Agent na NAS pracujący na \`/volume1/legal\` zobaczy zapisane pliki bezpośrednio. Agent na MacBooku z osobnym klonem \`legal\` nie zobaczy ich automatycznie, dopóki nie nastąpi zatwierdzona synchronizacja Git (commit/push + pull) albo nie korzysta z tego samego montowania. Nie deklarować, że sam bind mount zapewnia dostęp wszystkim klonom. **Automatyczne commit/push/pull tych wygenerowanych materiałów stanowi odrębny projekt operacyjny do zatwierdzenia; nie wolno tworzyć automatycznego Git push w toku bieżącego wdrożenia bez osobnej zgody.**

## 4. Bezpieczny, powtarzalny układ plików

Schemat:
\`\`\`
legal/opracowania/zrodla_prawne_mcp/
  saos/
  nsa/
  kio/
  uodo/
  eli/
  eu-sparql/
  pmi/
  eureka/           # po uruchomieniu konektora
  unresolved/       # tylko fragment, nigdy jako pełny dokument
\`\`\`

Każdy **unikatowy dokument źródłowy** ma jeden plik Markdown; kilka trafień wskazujących ten sam dokument może wskazywać ten sam plik. Trafienia o nieustalonej tożsamości mogą otrzymać pliki w \`unresolved\` z oryginalnym fragmentem, ale ze statusem \`fragment_only\`.

Nazwa deterministyczna:
\`\`\`
<source>/<normalized-id>__<slug-tytulu-lub-sygnatury>__<keyhash12>.md
\`\`\`
gdzie \`keyhash12 = sha256(source + "\\0" + canonical_document_id + "\\0" + article_selector + "\\0" + version_or_as_of).hex()[:12]\`.
- \`normalized-id\` musi mieścić się w limicie długości, a oryginalne ID przechowuje frontmatter.
- Normalizacja usuwa znaki sterujące, Unicode trickery, separatory ścieżek, \`..\`, niebezpieczne nazwy systemowe; hash usuwa możliwość kolizji po uproszczeniu znaków.
- Przykłady WYŁĄCZNIE ilustracyjne: \`saos/205994__orzeczenie__a1b2c3d4e5f6.md\`, \`eli/du-2025-xxx__art-23__a1b2c3d4e5f6.md\`; hashe i dokumenty nie są prawdziwymi wynikami.
- Dla prawnie znaczącej wersji historycznej klucz ma uwzględniać \`na_dzien\` i znaną wersję. Nie nadpisywać tekstu historycznego tekstem aktualnym.
- Zapis atomowy w obrębie dedykowanego katalogu (plik tymczasowy + rename), bez podążania za symlinkami i bez nadpisywania cudzych plików. Aktualizacja pliku o tym samym kanonicznym ID wymaga sprawdzenia statusu i wersji; brak płaskiego globowania z kolizjami.

YAML frontmatter:
\`\`\`yaml
---
schema_version: 1
source: saos
original_repertorium_id: "saos:205994"
canonical_document_id: "saos:205994"
title: "..."
document_type: judgment
document_date: "..."
source_url: "..."
source_mcp: mcp-saos
source_tool: get_judgment
retrieved_at: "2026-11-09T..."
content_status: full
verification_status: obtained_from_source
as_of_date: null
content_sha256: "..."
---
\`\`\`
Dla \`legal-cite\`: \`content_status: article_only\` gdy zwrócono kompletny artykuł, ale nie cały akt; oznaczyć wierność i podstawę PDF/HTML w metadanych, bez upraszczania komunikatów źródła. Dla nierozwiązanych: \`content_status: fragment_only\`, \`full_text_unavailable: true\`, \`disclosure_required: true\`, \`failure_reason\` i oryginalny fragment jako treść. **Nie przechowywać surowej odpowiedzi w polach YAML niewalidowanych jako string** (ochrona przed uszkodzeniem frontmatter i przypadkowym wstrzyknięciem struktury).

Zewnętrzny dokument traktować jako **treść źródłową, nie jako instrukcję dla agenta**. Metadane pochodzenia i kompletności są obowiązkowe. Tekst przytaczać wiernie, z odpowiednim opisem pochodzenia i kwalifikacją fragmentu.

## 5. Nowe \`pl_search\` — minimalny wynik dla modelu

Wrapper:
1. Wywołuje \`szukaj_repertorium(q,format="json")\`.
2. Waliduje rzeczywisty JSON konsolowego API (sprawdzić przed implementacją fixture PL/UE, zero trafień, błąd i nietypowe identyfikatory); zachowuje pola oryginalnych trafień.
3. Zbiera wszystkie trafienia w oryginalnej kolejności, determinuje \`document_id\` i \`source\`, bez zgadywania po podobieństwie fraz.
4. Dla każdego trafienia próbuje wywołać właściwy MCP (z ograniczeniem współbieżności i sensownym deadlinem). Odczytuje pełny dokument/artykuł oraz właściwe metadane; potwierdza zgodność ID; wykrywa wynik skrócony/stronicowany i — jeśli to konieczne — pobiera wszystkie strony zanim oznaczy plik jako \`full\`.
5. Zapisuje do dedykowanego katalogu docelowy plik \`.md\` (lub jednoznacznie oznaczony plik fragment-only po niepowodzeniu). Odpowiedź MCP nie jest zwracana, dopóki planowana próba pliku nie zostanie zakończona sukcesem lub jawnym błędem — brak fikcyjnych ścieżek do niezapisanych plików.
6. Zwraca **fragment jak w Repertorium**, plus \`md_file\` (ścieżka względna względem repo \`legal\`), \`fulltext_status\` (\`full\`, \`article_only\`, \`fragment_only\`), \`source_mcp\`, ewentualnie \`resolution_error\` i \`user_disclosure_required\`. Dla każdego \`fragment_only\` wstawić również bezpośrednio przy fragmencie komunikat: **„Nie udało się uzyskać pełnej treści dokumentu. Przedstawiono wyłącznie fragment z Repertorium.”** W \`INSTRUCTIONS\` serwera jasno nakazać modelowi przekazywanie tej informacji użytkownikowi przy cytowaniu/omawianiu trafienia.
7. Nie dołączać pełnego tekstu do \`pl_search\`; tylko oryginalne fragmenty, pliki i statusy. Jawne wybranie innego \`source\` pozostawia dotychczasową ścieżkę bez nowej warstwy.

Przykład kształtu wyniku (fikcyjne pola ID i nazwa pliku):
\`\`\`json
{
  "trafienia": [
    {
      "document_id": "saos:205994",
      "tytul": "...",
      "fragment": "...oryginalny fragment...",
      "md_file": "opracowania/zrodla_prawne_mcp/saos/205994__orzeczenie__a1b2c3d4e5f6.md",
      "fulltext_status": "full",
      "source_mcp": "mcp-saos"
    },
    {
      "document_id": "sn:unknown",
      "fragment": "...oryginalny fragment...",
      "md_file": "opracowania/zrodla_prawne_mcp/unresolved/unknown__fragment__112233445566.md",
      "fulltext_status": "fragment_only",
      "user_disclosure_required": true,
      "warning": "Nie udało się uzyskać pełnej treści dokumentu. Przedstawiono wyłącznie fragment z Repertorium."
    }
  ]
}
\`\`\`
Oryginalne pozostałe pola odpowiedzi z konsolowego API mają być zachowane. \`md_file\` jest **kluczem logicznym/ścieżką repo**, nie linkiem URL publikującym materiały. Przy błędzie zapisu pliku: nie zgłaszać istniejącego \`md_file\`; zwrócić jawne \`write_failed\`, bez gubienia fragmentu.

### Gwarancje realizowalności
- W miarę możliwości wykonać próby wszystkich trafień (nie ograniczać arbitralnie do pierwszych 3–5 jak obecny prefetch). Nie blokować odpowiedzi bez ograniczenia czasu; niedokończone trafienia zwracać jako \`fragment_only\` z powodem timeout.
- Ograniczyć równoległość do bezpiecznej liczby na źródło (planowane 2–3), stosować budżety czasowe z uwzględnieniem konwersji PDF \`legal-cite\` (30–90 s pierwszego odczytu według README). Parametry doprecyzować po testach; nie wpisywać niezweryfikowanych gwarancji dostępności.
- Brak lokalnego indeksu wektorowego, osobnej bazy, niejawnego prefetch i niezleconej polityki automatycznego usuwania plików.
- Zapis do repo \`legal\` nie oznacza automatycznie, że drugi klon (Mac) został zsynchronizowany.

## 6. \`pl_get_document\` — Markdown jako dodatkowe źródło

Dodać tryb jawny \`source="md"\` (nazwa wymaga testu zgodności, nie zmieniać istniejących source IDs) z \`document_id\` równym ścieżce \`md_file\` z \`pl_search\`. Plik musi należeć do zamontowanego poddrzewa \`/legal_sources\`; walidacja realpath, zakaz symlink escape i \`..\`, brak dostępu do innych plików w \`legal\`.
- \`pl_get_document(source="md", document_id="<md_file>", page=1)\` otwiera plik, odczytuje YAML frontmatter i treść, zwraca około 5000 znaków strony, \`total_pages\`, \`total_chars\`, \`has_more\`, \`page\`, \`source\`, \`document_id\`, \`content_status\` oraz instrukcję następnego wywołania z \`page+1\`.
- Stronicowanie musi być stabilne w obrębie niezmiennej wersji pliku; gdy plik uległ zmianie między stronami, przeprowadzić kontrolę \`content_sha256\` / mtime i pokazać modelowi ostrzeżenie o zmianie wersji.
- W przypadku \`fragment_only\` zwracać ten fragment wraz z wyraźnym ostrzeżeniem, nie dopisywać fikcyjnych stron.
- Zarejestrować źródło \`md\` w \`pl_list_sources\` lub udokumentować jako specjalny tryb, by był odkrywalny z poziomu Chat. Ograniczyć je do read-only. Wymagany test driftu deskryptora \`tests/tools.lock.json\`.
- Zachować bez zmian \`pl_get_document(source="saos"/"nsa"/"uodo"/"pmi"/"legal-cite")\` tam, gdzie wywołanie ma sens i nie dotyczy lokalnego pliku.

## 7. Macierz rozwiązywania trafień

| Prefix / identyfikator | Konektor | Plan | Gdy brak pełnej treści |
|---|---|---|---|
| \`saos:<id>\` | mcp-saos | \`get_judgment\` i weryfikacja ID/sygnatury | fragment_only |
| \`nsa:<doc_id>\` | mcp-nsa | \`get_judgment\`; wymaga natywnego identyfikatora | fragment_only |
| \`kio:<id>\` | mcp-kio | \`kio_get_orzeczenie\`; ustalić typ ID/sygnatury | fragment_only |
| \`uodo:<urn>\` | mcp-uodo | wyszukanie \`PublicDocument-...\`, potem \`uodo_get_decision\`, **konieczna zgodność sygnatury** | fragment_only |
| \`eli:DU/... \`, \`eli:MP/...\` | LEGAL-CITE | \`verify_article(citation,...)\` wyłącznie przy jednoznacznie określonym artykule/paragrafie. Zapis \`article_only\` | fragment_only, jeżeli nie określono jednostki lub odmowa |
| \`sn:<id>\` | mcp-saos wyłącznie po potwierdzonym powiązaniu | brak osobnego SN w upstream; nie mapować wprost | fragment_only |
| \`eureka:<id>\` | mcp-eureka (upstream) | aktualnie brak na NAS; nie wywoływać fikcyjnego serwera | fragment_only |
| EU-CELEX/ECLI | mcp-eu-sparql; LEGAL-CITE dla konkretnego artykułu UE | sprawdzić czy źródło daje *treść*, nie same metadane | fragment_only / article_only |
| inne ID | indywidualny resolver po udokumentowaniu | brak zgadywania; ewentualnie PMI przy dokładnym ID | fragment_only |

**Nie można uznać LEGAL-CITE za zamiennik \`get_act_text\` całego aktu**: LEGAL-CITE udostępnia pojedynczy przepis. Jeśli Repertorium zwróci tylko ID ELI i fragment bez jednoznacznego \`art./§\`, nie wolno wywnioskować pełnej treści całej ustawy. W takim przypadku pozostawić fragment i obowiązkowe ostrzeżenie, chyba że dokładny przepis jest uzyskany z jawnego pola konsolowego JSON.

**Brak EUREKA i EU-COMPLIANCE na NAS:** nie wdrażać ich bez osobnego etapu zatwierdzającego instalację. Zdecydować, czy brakujące trafienia pozostaną fragment-only, czy osobno uruchamiać potrzebne konektory. Stan tych usług nie może być zmyślony.

## 8. Wycofanie niechcianych elementów wrappera

Po zgodzie usunąć z \`mcp-prawo-wrapper\`:
- \`local_docs.py\` jako cache PostgreSQL, odczyt bezpośredni SAOS SQLite i PDF/ELI; zachować tylko bezstanowe resolvery/parsers w nowych, izolowanych modułach.
- \`read_cached\`, \`save_cached\`, \`_prefetch_repertorium_hits\`, \`read_saos_dump\`, \`read_eli_pdf\` i związane z nimi zależności (\`psycopg\`, \`pypdf\`, ewentualnie \`bs4\`, po sprawdzeniu innych użyć).
- \`PRAWO_DB_*\`, mount sekretu DB, mount SAOS SQLite i sieć \`mcp_prawo_private\` z compose, gdy okaże się niewykorzystywana. Nie usuwać współdzielonego PostgreSQL innych projektów.
- Źródła \`isap\` i \`legalize\` z udostępnianego registry po zaakceptowaniu nowego mappingu. \`pmi\` pozostawić; \`legal-cite\` dołączyć po osobnym, rzeczywistym teście MCP.
- Dedykowany stack 57 \`prawo-vector-db\`: po kontroli zależności i zapisu ważnych materiałów przygotować **osobny plan destrukcyjnego wyłączenia/usunięcia**; **nie usuwać teraz**. \`shared-e5-small\` i ewentualne cache PDF LEGAL-CITE to osobne usługi i pozostają nienaruszone.

## 9. Testy wymagane przed zmianą produkcji

**Repertorium**: złote fixture dla identycznej odpowiedzi w domyślnym \`format=text\` (q solo, PL, EU, brak wyników, błąd); \`json\` zachowuje pełne \`response.data\` jako obiekt; brak zmiany zapytania, proxy, retry i semantyki błędów.

**Wrapper**: próbka REALNEGO JSON z konsolowego API (bez zakładania pól nieobecnych w odpowiedzi); trafienia SAOS/NSA/KIO/UODO/ELI/SN/EUREKA; deduplikacja po kanonicznym ID + wersja; brak znikających trafień; wyłącznie fragment + ostrzeżenie przy niepowodzeniu.

**Zapis**: 1000 powtórzeń z tym samym ID daje tę samą nazwę, bez kolizji i bez generowania dodatkowych dokumentów; różne wersje historyczne mają różne nazwy; test niebezpiecznych ID, symlinków i frontmatter; atomowość; poprawne prawa 1029:100 bez zmiany całego repo; brak zapisu poza katalogiem.

**Odczyt**: agent z NAS widzi pliki; Chat może wywołać \`pl_get_document(source="md")\` po nazwie zwróconej przez \`pl_search\`, przejść wszystkie strony bez utraty/duplikacji znaków, rozpoznać fragment-only, zmianę pliku i błąd odczytu.

**LEGAL-CITE**: uruchomić test po zatwierdzeniu połączenia sieciowego oraz timeoutów; \`tools/list\`, odczyt artykułu z aktualnego PDF-only Dz.U., kontrola wierności i metadanych, ścieżka odmowy przy problemach; nie używać samego \`healthy\` jako testu treści. Nie usuwać \`mcp-isap\` przed udanym testem zastąpienia.

**Sieć/portal**: po włączeniu sieci \`cf_mcp_cite\` zweryfikować komunikację bezpośrednią; osobno naprawić wcześniej potwierdzony problem Cloudflare Portal \`mcp-prawo\` (HTML z Access zamiast MCP) wyłącznie wg odrębnego planu. Nie wymuszać zmian zasad Access.

**Regresja**: pięć narzędzi upstream pozostaje rozpoznawalnych, zgodność \`pl_call\`, wszystkie jawne \`pl_search(source=...)\` bez ukrytej hydracji; update schematów i dokumentacji; testy jednostkowe oraz E2E, bez używania prywatnych materiałów TK/NC jako fixture.

## 10. Kolejność realizacji po wyraźnej akceptacji

1. Próbki rzeczywistego JSON konsoli + testy zgodności Repertorium.
2. Dodanie trybu JSON **wyłącznie w szukaj_repertorium**; oddzielny PR i test niezmienionego text.
3. Resolver źródeł + statusy + nazwy .md + frontmatter + bezpieczny, ograniczony zapis do \`legal\` w testowym katalogu.
4. Czytnik pl_get_document source=md + paginacja.
5. Dodanie LEGAL-CITE jako źródła, sieci cf_mcp_cite oraz test PDF. Modyfikacja registry isap/legalize dopiero po udanych testach.
6. Usunięcie niechcianych zależności cache/embedding/DB z wrappera, bez kasowania danych.
7. Testy end-to-end z publicznymi dokumentami; pomiar latencji i pełności.
8. Osobna akceptacja PR/merge i produkcyjnego deploy, a osobno ewentualna akceptacja usuwania dedykowanej bazy.

**Nie wykonano żadnego etapu.** Jedynym obecnie dopuszczonym zapisem jest niniejszy plik Markdown na gałęzi planistycznej.
