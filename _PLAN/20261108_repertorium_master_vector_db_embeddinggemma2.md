# Plan DEV/TEST: Repertorium + MASTER DATABASE + benchmarking silników i embeddingów

Data: 2026-11-08. Status: DO AKCEPTACJI. Ten dokument nie jest zgodą na implementację, migrację ani usuwanie danych.

## Decyzje użytkownika

1. Reguła nienaruszalności upstream zostaje zniesiona. Można świadomie modyfikować fork; każda zmiana nadal wymaga uprzedniego planu Markdown i wyraźnej akceptacji.
2. Nie wracać do uvx/npx. Wszystkie istniejące MCP są osobnymi serwerami, a wrapper używa ich endpointów HTTP.
3. Domyślnie pl_search wykonuje federację Repertorium i MASTER DATABASE. Parametr source nadal pozwala jawnie wybrać określony MCP, wtedy nie stosować federacji.
4. Wyniki Repertorium są bazą listy dokumentów; MASTER DATABASE może dodać kolejne dokumenty, których Repertorium nie znalazło.
5. Zamiast fragmentów, dla każdego zidentyfikowanego dokumentu pobrać pełny tekst z master; gdy brak, pobrać przez odpowiedni MCP, skontrolować identyfikator i wersję, zapisać pełny dokument w master. Model dostaje tylko stronę pierwszą z pełną paginacją, a wszystkie strony pozostają w master.
6. Wyniki bez źródła/identyfikatora są obowiązkowo raportowane jako SOURCE_MISSING z oryginalnym fragmentem. Zakaz cichego pomijania lub zgadywania źródła.
7. To środowisko dev/test. Embeddingi nie są trwałymi danymi produkcyjnymi. Każdy model testować w osobnej przestrzeni/run_id, po teście umożliwić usunięcie tylko jego wektorów, nie pełnych tekstów. Nie usuwać nic teraz.
8. Bez wyboru pgvector, Qdrant czy LanceDB przed porównaniem według tych samych kryteriów i na tym samym zbiorze.

## Zastany stan (odczyty z Synology)

- PostgreSQL 16 z pgvector 0.8.7. Wersja pgvector jest aktualną stabilną (wydana 1.10.2026), ale samo rozwiązanie wybrano bez udokumentowanej analizy alternatyw.
- 16 pełnych dokumentów: ISAP 1, KIO 1, KRS 1, NSA 1, PMI 4, SAOS 7, UODO 1. Tabela legal_chunks pusta; 0 embeddingów i brak indeksów ANN.
- title, signature i source_url są puste we wszystkich 16 rekordach. Trzeba je uzupełnić na podstawie potwierdzonych źródeł, nie dopasowywać arbitralnie.
- Repertorium posiada narzędzie szukaj_repertorium(q), zwraca tekst opisowy, nie JSON. Test zapytania o art. 246 k.p.k. dał 7 rekordów z tytułami, fragmentami, document_id i linkami. Każdy rekord należy parsować osobno.
- PMI ma publiczny indeks 895 tytułów (sprawdzone przez pmi_list_acts), a nie pełny katalog polskiego prawa.

## Docelowy algorytm pl_search

1. Uruchomić równolegle wyszukiwanie Repertorium i w indeksie MASTER DATABASE; jawne zapytanie do konkretnego source nadal omija federację.
2. Parser ma odczytać KAŻDY wynik Repertorium i zachować pełny oryginał wpisu, numer w kolejności, document_id, fragment, tytuł, datę, source_url i źródło. Awaria parsera nie może ukryć rekordu.
3. W razie braku jednoznacznego źródła zapisać SOURCE_MISSING i zwrócić użytkownikowi/modelowi nieprzypisany fragment oraz licznik takich wyników. Nie wnioskować tożsamości z samego podobieństwa embeddingów.
4. Zachować wszystkie trafienia Repertorium w ich kolejności. Dodać osobno nowe dokumenty MASTER DATABASE. Deduplikować po kanonicznym source+ID+wersja, nigdy po podobieństwie tytułu; akt historyczny i tekst jednolity nie są identycznymi dokumentami.
5. Dla każdego trafienia z ważnym identyfikatorem: sprawdzić MASTER DATABASE i integralność tekstu. W razie braku pobrać natywne narzędzie MCP, zachować metadane, wersję, data pozyskania, URL i ewentualny hash. Do master trafia pełny dokument, nie tylko fragment.
6. Odpowiedź JSON zawiera documents[] z source, document_id, title, source_url, page=1, total_pages, total_chars, has_more, content(first ~5000 chars), provenance, master_status oraz oddzielne unattributed_fragments[] i errors[]. Kolejne strony przez pl_get_document z master, bez powtórnego pobrania upstream.
7. Niedostępne pełne teksty zwracać jako FULL_TEXT_UNAVAILABLE z pierwotnym fragmentem źródła i wyjaśnieniem, a nie jako pełny dokument. Timeout i limity pobrań muszą być jawne i nie mogą ucinać listy bez sygnału truncated_results.
8. Pomiar latencji etapów, statusów kompletności i błędów bez wycieku treści spraw prywatnych. Odrębnie rozstrzygnąć dotychczasowy ukryty prefetch.

## Porównanie silników

- PostgreSQL + pgvector 0.8.7: ACID, relacje, pełne teksty i metadane w SQL; 3072D może być przechowywane jako vector, ale indeks HNSW vector ma limit 2000D; halfvec HNSW 3072D jest możliwy z kompromisem precyzji. Wyszukiwanie BM25/hybrydowe trzeba zbudować lub dodać odpowiedni mechanizm.
- Qdrant: dedykowany ANN, wektory 3072D float32, BM25, sparse/dense hybrid, multivectors i ranking wieloetapowy. Minusy: osobna usługa i synchronizacja z master dokumentów lub zmiana wzorca składowania.
- LanceDB: embedded na SSD, vector + full-text + wyszukiwanie hybrydowe, łatwa izolacja eksperymentów; konieczny test współbieżności, trwałości i polskiej tokenizacji.
- Typesense: silne keyword/vector hybrid i ranking, bardziej silnik wyszukiwawczy niż relacyjny master; przetestować tylko gdy podstawowe trzy nie dadzą wystarczającej jakości.
- Nie usuwać PostgreSQL przed rozstrzygnięciem, czy ma pozostać MASTER DATABASE pełnych dokumentów, a Qdrant/LanceDB ma być jedynie pochodnym indeksem.

## Modele embeddingowe do testu

A. EmbeddingGemma 2, model Google wydany 6.10.2026, lokalny wariant text-only ok. 270M parametrów; pełny output 768 wymiarów. W pierwszym kroku sprawdzić możliwość uruchomienia na Synology CPU/RAM, nie zakładać wydajności.
B. gemini-embedding-2, Google API GA 22.04.2026, 8192 tokenów input i pełne 3072 wymiary. Nie jest modelem wydanym w październiku. Oddzielna przestrzeń embeddingów i świadoma zgoda na ewentualne koszty API.

## Benchmark — po akceptacji

- Zamrożony zestaw min. 30 zapytań (polskie przepisy, sygnatury, synonimy, podobne akty i daty, negacje, fałszywe trafienia) z niezależną listą prawidłowych źródeł i dokumentów.
- Najpierw eksperyment mały na 16 aktualnych dokumentach i siedmiu wynikach Repertorium; osobno benchmark skalowania na 200–1000 pełnych dokumentów z potwierdzoną proweniencją, tylko po aprobacie pobrania.
- Ten sam korpus, chunking ze strukturą art./paragraf/ustęp, prompt, kryteria rankingu, query set i warunki sprzętowe dla wszystkich modeli/silników. Zachować wersję modelu i run_id.
- Mierzyć embedding latency p50/p95, przepustowość, CPU/RAM/dysk, koszty API; retrieval Recall@5/@10, MRR@10, nDCG@10, source-attribution accuracy, pełność dokumentów, paginację, ranking po hybrydzie.
- Oddzielić czas generacji embeddingów od czasu ANN/BM25, wyraźnie oznaczać exact vs approximate, porównać quality/latency przy identycznym korpusie i parametrach.
- Wektory każdego modelu przechowywać jako wyraźnie oddzielne eksperymenty; można usunąć wektory wybranego run_id dopiero po osobnym zatwierdzeniu, nie kasując treści ani metadanych.
- Zakończeniem jest porównawczy raport Markdown, rekomendacja silnika i odrębny plan/akceptacja ewentualnego wdrożenia.

## Zasada procesu

Dopuszczone teraz: audyt, odczyty, zapis tego pliku na gałęzi audit. Nieautoryzowane: wdrażanie nowych silników, restart, zmiana kodu źródłowego, schematu DB, generacja wektorów na NAS i kasowanie jakichkolwiek danych. Każda implementacja po zatwierdzeniu konkretnej fazy planu.
