# SNAPSHOT AUDYTOWY / HAND-OFF — LOCAL-FIRST, PDF ELI, CELEX/RODO/ECLI, Webwright SN/MS/TK

**Data:** 2026-10-31 (Europe/Warsaw)  
**Cel dokumentu:** pozwolić niezależnemu modelowi sprawdzić stan rzeczywisty, wykryć błędy wcześniejszej implementacji, odtworzyć decyzje i wdrożyć jedynie niezbędne poprawki.  
**Status:** analiza repo `apiotrowski-afk/legal-cite-pl` + stan roboczych PR. NIE wykonano cherry-pick jego kodu do resolvera, NIE wdrożono nowych kontenerów, NIE modyfikowano REPERTORIUM.  
**Zakaz:** nie zmieniać nic w `mcp-repertorium` (kod, kontener, konfiguracja, portal endpoint, baza ani routing). Nie wyłączać produkcyjnych źródeł bez E2E.

## 1. Czego chcemy

Model ma mieć w portalu `lex` **dokładnie 2 narzędzia prawne**:
1. Istniejące `szukaj_repertorium` służące do wyszukiwania/identyfikacji źródeł — bez zmian.
2. Nowe `pobierz_dokument`, przyjmujące dokładne `document_id` z Repertorium lub Dz.U./M.P./CELEX/ECLI/RODO/sygnaturę i zwracające autentyczne źródło/fragment z metadanymi, paginacją i poziomem wierności.

Narzędzie `pobierz_dokument` działa kolejno: **lokalny korpus USTAWY/SAOS/polski UE → trwały cache resolvera → tylko w razie braku oficjalne API/Cellar/Webwright → kontrola integralności i zgodności → zapis trwały w lokalnej bazie → ponowny odczyt bez sieci**. Nie powielać indeksu SAOS; wykorzystać jego mirror. Oryginalne PDF zachować z SHA-256. Zawsze oddzielać: (a) wierne odczytanie, (b) kompletność obiektu, (c) aktualność prawną w danym dniu, (d) status urzędowy/nieważące opracowanie.

Dla MS, SN i TK Webwright jest **wewnętrznym MCP** wywoływanym wyłącznie na lokalnym cache miss. Nie dodawać jego tooli do publicznego `lex`. Docelowa baza lokalna rośnie o nowe, **zweryfikowane** dokumenty. Snippet/challenge/odnośnik/strona szczegółów nie jest pełną treścią orzeczenia.

## 2. Dowody: aktualna infrastruktura i odpowiedzi

- Na Synology/Portainer uruchomione m.in. `mcp-repertorium` port 8410, `mcp-ustawy` 8412, `mcp-saos` 8402, `mcp-nsa` 8405, `mcp-eu-sparql` 8408, `mcp-eu-compliance` 8409. Z poprzedniego testu `mcp-repertorium` zwrócił 8 rezultatów dla `art. 23 ustawy o ochronie zdrowia psychicznego`: `eli:DU/2024/917`, `saos:166511`, `nsa:389F2C5B67`, `sn:hFvgRJcBZvGrB8P_afyJ`; dla `RODO art. 33` 9 wyników, m.in. `celex:32016R0679:pl`; dla dokładnego numeru Dz.U. także false positives. Takie ID należy ROZWIĄZYWAĆ deterministycznie.
- `USTAWY` w działającym MCP mają **37 indeksowanych aktów**, m.in. `DU/2024/917` (ustawa o ochronie zdrowia psychicznego, 74 artykuły). Istniejący `ustawy.py` bazuje na SQLite FTS5, artykułach z `git-as-law`/komentarza, a nie na kompletnym archiwum oryginalnych PDF Dz.U. Brak bind mountu do bazy w działającym kontenerze USTAWY; używać wewnętrznego API/MCP lub opcjonalnego read-only snapshotu. Nie utożsamiać tekstu artykułów z pełną publikacją i wszystkimi załącznikami.
- `SAOS` utrzymuje własny lokalny mirror i fallback do API. `NSA` nie ma potwierdzonego równoważnego mirrora; nowy PR NSA obsługuje offset/limit.
- `EU-COMPLIANCE` ma lokalny **angielski** korpus 14 regulacji; nie używać jego brzmienia jako urzędowego PL. `EU-SPARQL` znajduje CELEX/ECLI/TSUE, ale sam nie gwarantuje pełnego aktu czy orzeczenia.
- Portal `lex` w ostatnim odczycie miał **56 narzędzi / ~79 376 znaków schematów** i nie pokazywał REPERTORIUM mimo działającego kontenera. Nie wyłączać starej listy, dopóki **oba** docelowe narzędzia nie są realnie widoczne przez portal z dotychczasowym uwierzytelnieniem.

## 3. Aktualny kod w elconcept — wykonane zmiany, gałęzie i stan

### A. `elconcept/mcp-prawo-wrapper`

**Draft PR #4:** https://github.com/elconcept/mcp-prawo-wrapper/pull/4  
Gałąź `feat/minimalny-resolver-repertorium-20261031`, ostatni zweryfikowany HEAD **`5fb202b79796b60876c12ef967559a27bbfada5d`**. Bazuje na gałęzi `fix/upstream-native-pagination-20261031`, której draft PR **#3** (HEAD `382d0aeb5a13be3f4bb5398c8f04c3d3a5a8273f`) naprawia utratę `structuredContent` i natywną paginację SAOS/NSA. Dlatego diff PR #4 względem `main` wymaga uwzględnienia PR #3.

- `src/prawo_pl_mcp/slim_resolver.py`: osobna instancja FastMCP z **1** publicznym `pobierz_dokument`; parse ID ELI/SAOS/NSA/CELEX/RODO/ECLI/SN/EDPB/MS/EUREKA, lokalne źródła i fallback.
- `src/prawo_pl_mcp/local_corpus.py`: SQLite read-only USTAWY, cache `documents`, `fragments`, `candidates`, walidacja SHA, opcjonalny `PRAWO_EU_PL_SQLITE`. Cache w **osobnej** bazie, bez bezpośredniego nadpisywania USTAWY lub SAOS.
- `src/prawo_pl_mcp/browser_bridge.py`: wywołuje prywatny Webwright MCP dopiero po braku lokalnego dokumentu.
- `src/prawo_pl_mcp/webwright_internal.py`: wewnętrzne 2 toole — CELEX PL i SN po sygnaturze. `ms` i `tk` mają status `adapter_niegotowy`; nie udawać ich obsługi.
- `vendor/webwright_legal_pl/scripts/fetch_{eurlex,orzeczenie}.py` i LICENSE: oryginalne skrypty z `matematicsolutions/awesome-matematic-skills-pl` (rewizja `e99b534`), Apache-2.0. Skrypty zapisują `meta.json`, markdown strony, screenshot i adres PDF.
- `src/prawo_pl_mcp/pdf_ingest.py`: **tymczasowy** odczyt PDF przez `pypdf`, whitelist SN/EUR-Lex, heurystyczna identyfikacja CELEX/sygnatury, zapis oryginalnego PDF i tekstu pod SHA-256.
- `src/prawo_pl_mcp/slim_asgi.py` + `webwright_asgi.py`, `deploy/minimal-legal/{Dockerfile.resolver,Dockerfile.webwright,compose.staging.yaml}`: dwa obrazy staging, prywatna sieć, wolumen cache/artefaktów, w `lex` NIE zarejestrowano żadnego.
- `tests/test_{slim_resolver,local_corpus,pdf_ingest}.py`: testy przygotowane; **nie było pełnego pytest/CI** dla tej gałęzi.

**Wykonane testy lokalne (wcześniejsza sesja, nie CI):** Python AST, parser 9 ID, mock SQLite USTAWY exact ELI, test SHA cache, fragmentów SAOS oraz symulowany PDF. Działający serwer Repertorium/USTAWY był używany do testów odczytowych. Nie było Docker build + prawdziwego browser/PDF E2E.

### B. `elconcept/grounding-prawo`

**Draft PR #81:** https://github.com/elconcept/grounding-prawo/pull/81  
Gałąź `feat/eli-local-resolver-20261031`, HEAD `202de127458e1db75d7966f05b65cdaf9a557b79`.
- `own-skills/patron-prawo-pl-zrodla/scripts/ustawy.py`: `Baza.akt_po_eli(eli,offset,limit,art)` — dokładny lokalny odczyt artykułów z SQLite + natywne strony, `dokument_pelny=false`.
- `own-skills/patron-prawo-pl-zrodla/scripts/ustawy_mcp.py`: wewnętrzne narzędzie `akt_po_eli` dla resolvera.
- Mock test SQLite tego endpointu **zaliczony** (exact ELI, strony, out_of_scope), ale CI **NIEZALICZONE**: https://github.com/elconcept/grounding-prawo/actions/runs/41149480617, job `build` #124382307998, krok `plugins/ zgodny z buildem`. Log: `plugins/ nie odpowiada źródłom: uruchom scripts/build.py i dołącz wynik do commita`. Inne testy wcześniejsze w tym jobie przeszły. NIE scalaj przed naprawą wygenerowanych artefaktów `plugins/` i ponownym zielonym CI. Uwaga na rozrost zmiany — nie dotykać Repertorium.

### C. Pozostałe PR-y

- `mcp-eu-compliance` draft PR #1 https://github.com/elconcept/mcp-eu-compliance/pull/1 — monolityczne połączenie EU-COMPLIANCE i SPARQL, **niezgodne z późniejszą decyzją** o pozostawieniu oddzielnych kontenerów za 2-tool portalem; nie scalać bez nowej decyzji.
- `mcp-eu-sparql` draft PR #1 https://github.com/elconcept/mcp-eu-sparql/pull/1 — wymuszenie PL, brak selektora i deduplikacja; niezależnie rozważyć.
- `mcp-krs` / `mcp-nsa`: osobne drafty naprawcze z poprzednich etapów; nie potrzebują udostępniania wszystkich endpointów modelowi.
- REPERTORIUM: **zero commitów, zero zmian uruchomionej konfiguracji**.

## 4. Nowe źródło: `apiotrowski-afk/legal-cite-pl`

Repo: https://github.com/apiotrowski-afk/legal-cite-pl  
Audytowany **main HEAD `2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988`** (commit 2026-10-29), licencja Apache-2.0. Nie korzystać bez przypięcia wersji. Zależność `eli2md @ git+https://github.com/PolskiAgentW/eli2md@v0.6.70` (MIT) przypięta do tagu; `poppler-utils/pdftotext`; `httpx`, `mcp>=1.2,<2`. Obecny wrapper używa `fastmcp>=3.4,<4` — **nie kopiować całego stosu zależności bez analizy konfliktów; preferować niezależny prywatny worker/warstwę parsera**.

### Co kod REALNIE robi (a nie tylko opis README)

| Funkcja/plik | Wartość do transplantacji | Ważne ograniczenie |
|---|---|---|
| [`pdf_tj.py::odczyt`](https://github.com/apiotrowski-afk/legal-cite-pl/blob/2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988/legal_cite/pdf_tj.py#L732) | ELI PDF + SHA, cache wyników konwersji pod SHA PDF i wersję konwertera, semafor CPU | Aktualnie pobiera PDF przez API samodzielnie; do Webwright należy dodać wejście `ścieżka/bytes` wcześniej zweryfikowanego pliku, bez ponownego pobrania |
| `pdf_tj.py::jednostki_md`, `przypisy_md` | Strukturalne artykuły/paragrafy, hierarchia jednostek, numery z indeksami, przypisy, wybór brzmienia wg daty | Zależność od `legal_cite.core` (m.in. `_data_wejscia`, `_wybierz_brzmienie`). Nie działa jako jeden skopiowany standalone plik |
| `pdf_tj.py::wiernosc_pdftotext`, `_tokeny_pdftotext`, `wyjasnienia_warstwy` | **Drugie niezależne czytanie** warstwy PDF + dokładna kontrola braków/przestawień słów; nie pomijać słów tylko dlatego, że występują w dowolnym przypisie | Dedykowane tekstom aktów, nie używać bezpośrednio do wyroków SN/MS/TK |
| `core.py::_teksty_jednolite`, `_nowelizacje_po`, `_aktualnosc_pl`, `_odpowiedz_pdf` | Wybór **najaktualniejszej wersji** przed formatem (HTML/PDF), rozróżnianie nowelizacji po t.j., przyszłych i nieustalonych | To logika aktualności prawnej, **odrębna od wiernego odczytu PDF**. Nie nadpisywać historycznych wersji samym ostatnim brzmieniem |
| `core.py::_wersja_eu`, `_fetch_eu`, `extract_eu_article` | CELLAR/XHTML po polsku + SPARQL wykrywający konsolidacje CELEX `0…-YYYYMMDD` i zmiany po konsolidacji; próbuje CELLAR zanim EUR-Lex za WAF | Dotyczy **aktów** UE; NIE pobiera automatycznie pełnych uzasadnień po ECLI, a konsolidacja jest nieurzędowa |
| `na_dzien.py` | Odczyt przepisu na wskazaną datę | Dużo zależności od `core`; przenieść dopiero po stabilizacji głównego local-first |

Oryginalne `legal-cite` expose'uje **dwa** narzędzia `verify_article` i `list_acts`; **nie należy dodawać ich do docelowego portalu** (mamy limit 2: Repertorium + resolver). Można korzystać z jego modułów jako wewnętrznego pracownika lub zaadaptować ich kod do warstwy ingest.

### Różnica w jakości względem obecnego `pdf_ingest.py`

Obecny `pdf_ingest.py`:
1. `pypdf` wyciąga tekst wszystkich stron.
2. Heurystyka szuka wystąpienia numeru aktu lub sygnatury.
3. Gdy tekst długi i ID występuje, zapisuje PDF+tekst i daje `zweryfikowany_tekst_zapisany`.

**TO NIE JEST pełna kontrola wierności:** ID może wystąpić tylko w cytowaniu innej sprawy, słowa mogą zniknąć, kolejność mogą zmienić kolumny, formatowanie przepisów może błędnie połączyć różne brzmienia. Dotychczasowe twierdzenie, że taki PDF jest „zweryfikowany” oznacza wyłącznie **weryfikację pobrania/ID, nie wierności odczytu**. Trzeba poprawić nazewnictwo/statusy przed dopuszczeniem do wiążących cytowań.

W `legal-cite-pl` PDF jest przetwarzany przez **eli2md (pdfplumber) oraz niezależny pdftotext**. Testy ochronne badają wycięcie prawidłowego artykułu i słowa w odpowiedniej kolejności, z maską jedynie nagłówków i przypisów, plus porównanie ze starszym HTML. Autor w README raportuje 99,7% zaliczonych artykułów w próbie z 2026-10-10, ale **nie odtworzono tego pomiaru** w Twoim środowisku. Nie traktować raportu autora jak własnego zielonego CI.

### Proponowany podział cherry-pick / adaptacji

**P0-A: ELI PDF-only (konieczne):**
1. Zachowaj local USTAWY -> cache jako priorytet; dla brakującej żądanej pozycji/artykułu używaj **oficjalnego ELI** tylko jako fallback. Pobierz metadane tekstu jednolitego (najpierw wersja, potem format, z oznaczeniem daty) wg `_teksty_jednolite`. Aktualna gałąź resolvera, gdy `textHTML=false`, zwraca **tylko link do PDF** — to luka do usunięcia.
2. PDF oficjalny → SHA → `eli2md@v0.6.70` → drzewo artykułów → `pdftotext` → `wiernosc_pdftotext` → porównanie ze starszym HTML, jeśli dostępne. W razie niejednoznaczności **odmów i oddaj link do oryginału**. Przy zaliczeniu zapisz oryginał, Markdown, tekst i raport jakości, z dokładną wersją konwerterów.
3. Zapisz do trwałego cache z `source_id`, `version_id`, `valid_from`/stanem prawnym, `sha256_pdf`, `sha256_tekst`, `parser_version`, `quality_status` i `language`. Separuj `snapshot_stan_na` od `pobrano_at`.
4. Wymagany test: najnowszy tekst jednolity HTML=false, starszy HTML=true; artykuł zmieniony po starszym t.j.; przyszłe brzmienia; p.p.s.a./k.p.k. i kodeksy; odmowa przy przesuniętym/zgubionym słowie; nieudane PDF i stary cache.

**P0-B: EUR-Lex CELEX/RODO (pierwsza ścieżka powinna być lokalna):**
1. Urzędowy polski korpus (nie EN EU-COMPLIANCE) -> lokalny cache -> **CELLAR XHTML PL** wg `_fetch_eu` (preferowane, bo jest interfejsem maszynowym) -> dopiero ewentualnie Webwright EUR-Lex PDF/HTML.
2. Zweryfikować czy chodzi o tekst pierwotny CELEX `3…` czy nieurzędowy skonsolidowany `0…-data`. Nie podmieniać bez informowania. Aktualność określić względem daty i zmian po konsolidacji.
3. Sam `RODO art. 33` nie oznacza, że cała angielska baza nadaje się do polskiego cytatu; zachować polskie granice artykułów i oznaczenia źródła.
4. Wersjonowany cache danych EU może korzystać z mechanizmu `pdf_tj` **tylko tam, gdzie poprawnie obsługuje format aktu**; do HTML/XHTML CELLAR preferować strukturalny parser, nie Playwright. ECLI wyroków TSUE **nie** jest tym samym co CELEX rozporządzenia.

**P1-C: Webwright SN/MS/TK (nie transplantować struktury art./par.):**
1. Dla PDF orzeczeń zastosować ogólne dwuczytnikowe porównanie `pypdf/pdfplumber` vs `pdftotext`, a następnie identyfikację sygnatury **w nagłówku**/metadanych orzeczenia (nie w dowolnym cytacie), datę, sąd, sentencję i kompletność uzasadnienia.
2. Zachowaj PDF w postaci oryginalnej, ekstrakt i raport; jeśli skan bez warstwy tekstowej → jawne `requires_ocr` i osobny OCR ze wskazaniem, że nie jest to tekst urzędowo wyodrębniony. Nie nadawać `verified` na sam numer występujący w tekście.
3. W oryginalnym Webwright są **tylko** skrypty SN oraz EUR-Lex. Adaptery `orzeczenia.ms.gov.pl` i `trybunal.gov.pl` trzeba dopiero napisać i przetestować — szczególnie różne warianty HTML, PDF, blokady i formularze. Nie omijać CAPTCHA ani uwierzytelniania.

**Zalecenie:** nie wykonywać bezrefleksyjnego `git cherry-pick` jednego commita: `pdf_tj.py` jest mocno sprzęgnięty z `core.py`, a `legal-cite` ma inny zestaw zależności. Najbezpieczniej skopiować **przypiętą wersję modułów na osobną gałąź** z zachowaniem Apache-2.0 i MIT `eli2md`, wydzielić małą usługę ingest/parse PDF działającą wewnątrz Docker network, z API po stabilnej strukturze danych; nie eksponować modelowi nowych narzędzi. Stopień wspólności ELI i orzeczeń ograniczyć do pobierania, kontroli źródła, raw PDF/sha i ogólnej analizy tekstowej.

## 5. Blokery / błędy wykryte w istniejących draftach — DO POPRAWY, NIE UKRYWAĆ

**P0 krytyczne:**
1. `slim_resolver.py::_eli`: przy `textHTML=false` aktualnie zwraca `tylko_link`, **nie czyta PDF**. Wymaganie użytkownika niespełnione dla nowych t.j.
2. `pdf_ingest.py::_verified_identity` + `ingest_verified_pdf`: heurystyka sygnatury/CELEX nie dowodzi wierności ani kompletności treści, a wynik może dostać `dokument_pelny=true` i trafić do `save_cache`. Do czasu przeniesienia walidacji z legal-cite **zablokować awansowanie do trusted cache** albo zmienić flagę na `extracted_unverified`.
3. `local_corpus.py::save_cache` uważa dowolne ≥100 znaków HTTPS z `źródło` i `kompletny=true` za kompletne; nie weryfikuje provenance/version/parser. To słaba bramka. `_eli` może zapisać wyciągnięty HTML bez załączników jako `dokument_pelny=true`.
4. `slim_resolver.py`: pola `dokument_pelny=true` są pokazywane nawet na pierwszej z wielu stron (oznacza co najwyżej pełny *obiekt w cache*, nie pełną *odpowiedź*). Rozdzielić `kompletnosc_magazynu` od `dalszy_fragment` i `tekst_odpowiedzi_pelny`.
5. `sn:<opaque-id>` + osobny parametr `sygnatura`: obecny kod promuje PDF potwierdzony wystąpieniem *podanej* sygnatury do cache pod opaque-ID z Repertorium, **bez wiarygodnego dowodu, że oba identyfikatory dotyczą tego samego orzeczenia**. Zablokować promowanie dopóki brak mapowania/provenance.
6. `local_corpus.read_eu_pl(celex, artykul)` **ignoruje `artykul`** i zwraca cały akt. Obecny resolver wyświetla w odpowiedzi pole artykułu jako wskazanie, lecz faktycznie stronicuje cały tekst; dodać drzewo artykułów.
7. `local_corpus.save_fragment`: waliduje `returnedLength` z metadanych, ale **nie porównuje tego z długością przechwyconego tekstu**; `POOL.call_with_metadata` może zwracać treść z nagłówkami/uwagami serwera, co grozi zapisaniem fragmentu nieodpowiadającego offsetowi. Wymaga ścisłego kontraktu surowego fragmentu i testów 1+2+last dla SAOS/NSA.
8. `PRAWO_EU_PL_SQLITE` jest na razie tylko ścieżką/kontraktem cache. Nie ma wdrożonego ETL oficjalnego polskiego korpusu i wersji skonsolidowanych.

**P1 procesowe:**
9. `grounding-prawo` PR #81 — **CI czerwone** na synchronizacji generowanych `plugins/`; niezaliczone do merge. Regeneracja `scripts/build.py` zgodnie z workflow jest niezbędna.
10. `mcp-prawo-wrapper` PR #4 — **brak GitHub Actions runs** dla gałęzi; testowano tylko moduły na danych symulowanych w kontenerze; brak uruchomionego MCP, Docker build i żywej strony sądu/ELI/EUR-Lex.
11. `Dockerfile.webwright` dodaje `pypdf`, ale nie ma pin `eli2md`, poppler `pdftotext` ani testu wersji. Wdrożenie ekstrakcji legal-cite wymaga zmiany obrazu.
12. Fallback ELI/Cellar/Playwright może masowo obciążyć źródła; wymagane single-flight dla tych samych ID, bounded concurrency, budżet retry/timeout, negatywny TTL i telemetria hit/miss/cache/fidelity. Poprzednie repo utrzymuje semafor pojedynczej konwersji `_KONWERSJE=Semaphore(1)`.

## 6. Samodzielny plan kontroli przez drugi model

**Etap A — weryfikacja read-only, bez zmian:**
1. Otwórz SHA `2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988` w legal-cite, przeczytaj całe `legal_cite/pdf_tj.py`, `core.py` (szczególnie `_odpowiedz_pdf`, `_teksty_jednolite`, `_fetch_eu`), `na_dzien.py`, `pyproject.toml`, `testy/wiernosc_warstwy.py` i `testy/pdf_wiernosc.py`.
2. Otwórz `mcp-prawo-wrapper` PR #4 i `grounding-prawo` PR #81, sprawdź powyższe 12 ryzyk **linijka po linijce**; oceń importy, typy transportu FastMCP, PATH wolumenów, poprawność meta.json i schematów, integralność/kompletność, retry.
3. Zaloguj własne wyniki testów jako `PASS/FAIL/NOT RUN`, rozdzielając testy mocków od testów realnego ELI, EUR-Lex, SN, MS, TK, SAOS i NSA; zacytuj commit/test/log. Nie polegaj wyłącznie na README ani relacji poprzedniego modelu.
4. Odnotuj czerwony CI PR #81 (run 41149480617) i brak CI PR #4; nie zgłaszaj gotowości do merge.

**Etap B — adaptacja bez zmiany architektury:**
1. W osobnej gałęzi zbuduj **wewnętrzny** parser/worker PDF kompatybilny z lokalnym cache, adaptując przypięty `eli2md`, `pdftotext`, strukturalny parser i testy wierności `legal-cite`.
2. Najpierw zablokuj niezweryfikowane awanse PDF w starym kodzie. Zdefiniuj kontrakt source provenance + wersja + etykieta statusu: `official_html` vs `unofficial_verified_pdf_extract` vs `candidate` vs `ocr_unverified`; osobno status aktualności na datę.
3. Upewnij się, że **identyczny** `DU/2024/917 art. 23` jest pobierany z USTAWY **bez jednego wywołania sieci**, że inny numer idzie do fallbacku i jest zapisywany lokalnie; raz pobrany PDF ma się odczytywać po restarcie bez API.
4. `RODO art. 33` z lokalnego polskiego korpusu lub CELLAR PL (nie EN), CELEX wersje skonsolidowane/osobne daty; ECLI orzeczeń TSUE to osobna ścieżka.
5. Dla SN/MS/TK dodaj parser orzeczniczy z kontrolą sygnatury *w nagłówku*; jeśli pełnego orzeczenia brak, nie oznaczaj jako kompletnego; testy regresji na rzeczywistych oficjalnych dokumentach.
6. Napraw generowane artefakty w PR #81 i pełne CI, zbuduj obie usługi staging, wykonaj E2E i testy cache hit/miss, w tym restart. Dopiero po tym rozważ merge/produkcyjne przełączenie.

**Etap C — odbiór:**
- Model w `lex` widzi **wyłącznie** `szukaj_repertorium` i `pobierz_dokument`. Pośrednie MCP działają wewnętrznie, ich szczegółowe schematy nie zapychają kontekstu.
- Zmiany **nie obejmują** REPERTORIUM. Każda próba modyfikacji tego serwera jest niezgodna z zakresem.
- Dla każdego źródła: surowy PDF i SHA, tekst/cytowanie, identyfikator i wersja, rozróżnienie formy urzędowej, dowód wierności, raport kompletności, status aktualności; brak „success” po samym linku/snippe­cie.
- Negatywne testy: obcy wyrok z sygnaturą tylko w cytowanym uzasadnieniu, brak strony w PDF, zgubione słowo, dwukolumnowy PDF, tekst jednolity z przyszłym brzmieniem, brak lokalnej bazy, błąd API, nieoczekiwane przekierowanie, PDF+HTML sprzeczne, błędny offset/nextOffset, niezgodny sha.
- Testy kosztu: procent cache hit, liczba zewnętrznych fetch na żądanie, czas/rozmiar konwersji i ilość narzędzi widocznych modelowi.

## 7. Gotowy prompt dla modelu audytora

> Przeczytaj `_PLAN/20261031_SNAPSHOT_AUDYT_legal_cite_pl_local_first.md` w gałęzi `elconcept/mcp-prawo-wrapper:feat/minimalny-resolver-repertorium-20261031`. Nie ufaj relacji poprzedniego modelu — porównaj źródło `apiotrowski-afk/legal-cite-pl` na SHA `2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988` z kodem PR #4 i USTAWY PR #81. Oceń metodologię ekstrakcji PDF ELI i Webwright, kompletność/wierność/aktualność i cache local-first, w szczególności 12 wskazanych ryzyk. Podaj tabelę PASS/FAIL/NOT RUN z plikami/wierszami i dowodami. Następnie zaplanuj lub wykonaj bezpieczny adaptacyjny cherry-pick modułów (nie całego repo) na osobnej gałęzi; zachowaj licencję Apache-2.0 i pin MIT eli2md. Bez pełnych testów nie merge'uj i nie deployuj. REPERTORIUM bez jakichkolwiek zmian, w docelowym portalu tylko 2 narzędzia.

## 8. Linki/źródła

- legal-cite-pl commit: https://github.com/apiotrowski-afk/legal-cite-pl/tree/2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988
- PDF module: https://github.com/apiotrowski-afk/legal-cite-pl/blob/2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988/legal_cite/pdf_tj.py
- ELI / currency: https://github.com/apiotrowski-afk/legal-cite-pl/blob/2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988/legal_cite/core.py
- Author's PDF test: https://github.com/apiotrowski-afk/legal-cite-pl/blob/2c4b7bf6e2af56b42b8b87a9bdbfe93d8078c988/testy/pdf_wiernosc.py
- Wrapper code: https://github.com/elconcept/mcp-prawo-wrapper/pull/4
- USTAWY local ELI: https://github.com/elconcept/grounding-prawo/pull/81
- USTAWY failed workflow: https://github.com/elconcept/grounding-prawo/actions/runs/41149480617
- Webwright upstream: https://github.com/matematicsolutions/awesome-matematic-skills-pl/tree/e99b534/orzecznictwo-zrodla/skills/webwright-legal-pl
- `eli2md` pinned tag v0.6.70: https://github.com/PolskiAgentW/eli2md/tree/v0.6.70

**Ostateczny status: AUDYT PRZYGOTOWANY; CHERRY-PICK LEGAL-CITE NIE WYKONANY; IMPLEMENTACJA STAGING NIEGOTOWA DO PRODUKCJI.**
