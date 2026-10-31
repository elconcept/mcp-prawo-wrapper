# Architektura 2 narzędzi — REPERTORIUM + bezpośredni resolver dokumentów

Data analizy: 2026-10-31. Status: **projekt wdrożeniowy, bez zmian w REPERTORIUM, bez przełączania produkcji**.

## Decyzja

Zamiast pokazywać modelowi oddzielne wyszukiwarki SAOS, NSA, KRS, USTAWY, EU-SPARQL i EU-COMPLIANCE, udostępnić w portalu prawnym **tylko dwa narzędzia**:

1. `szukaj_repertorium(q, jurysdykcja?)` — **bez zmian w istniejącym kontenerze**. Używać do szerokich zapytań semantycznych i odszukiwania identyfikatora.
2. `pobierz_dokument(identyfikator, artykul?, strona?, adres_zrodlowy?)` — nowy, wąski resolver. Korzystać z oryginalnych dokumentów po deterministycznym identyfikatorze, bez ponownego wyszukiwania semantycznego.

`jurysdykcja=pl|eu` jest filtrem zakresu prawnego, NIE przełącznikiem języka. Wszystkie komunikaty po polsku. Publiczne narzędzia nie powinny mieć selektora języka.

## Udokumentowane testy rzeczywistych wyników (MCP HTTP /mcp na działającym mcp-repertorium, read-only)

| Zapytanie | Jurysdykcja | Liczba trafień | Identyfikatory/cechy |
|---|---|---:|---|
| art. 23 ustawy o ochronie zdrowia psychicznego | pl | 8 | `eli:DU/2024/917`, `nsa:389F2C5B67`, `saos:166511`, `sn:hFvgRJcBZvGrB8P_afyJ` |
| II SA/Wa 1353/19 | pl | 8 | `nsa:389F2C5B67` jako trafienie dokładne, ale obok inne lata i przypadkowe wzmianki |
| Dz.U. 2024 poz. 917 | pl | 8 | `eli:DU/2024/917` jako trafienie dokładne, ale także `eli:DU/2025/917`, `eureka:646788`, `ms:...`, `saos:...` |
| RODO art. 33 | eu | 9 | `celex:32016R0679:pl`, `celex:62022CJ0769:pl`, `edpb:binding-decision-12026-on-the-dispute-submitted-by-the-belgian-sa:pl` |

Wyniki REPERTORIUM zawierają **tytuł, datę, document_id, snippet, zrodlo_url/link, opcjonalnie sąd**. Aktualny MCP formatuje je **tylko do `content`**; nie zwraca ustrukturyzowanego `structuredContent.citations`. Tego serwera **nie zmieniać**.

**Krytyczne obserwacje:**
- REPERTORIUM jest dobrym *discovery*, ale nie mechanizmem gwarantującym dokładny wynik. Na przykład pytanie o Dz.U. 2024 poz. 917 zwraca też zbieżne pozycje, kwoty i sygnatury.
- `document_id` z prefiksem jest stabilnym punktem startu dla resolvera, ale nie każdy identyfikator jest publicznie rozwiązywalny.
- `celex:32016R0679:pl` zwracał w tym teście URL **EN**, mimo oznaczenia języka PL. Resolver musi wygenerować/zweryfikować odnośnik do oficjalnej polskiej wersji, a nie ślepo kopiować URL wynikowy.
- Dostępne w portalu `lex` przez Code Mode: **56 narzędzi, ok. 79 376 znaków JSON samych nazw, opisów i inputSchema**, w tym BASIC-MEMORY 29 narzędzi i ok. 57 405 znaków. **REPERTORIUM nie ma na aktualnej liście narzędzi ani serwerów lex**, choć kontener `mcp-repertorium` działa i odpowiada po HTTP na NAS (port LAN 8410). Nie wyłączać innych źródeł, dopóki portal nie udostępnia obu nowych narzędzi.

## Kanoniczny kontrakt resolvera

Narzędzie: `pobierz_dokument`, **jeden parametr wymagany** `identyfikator: string`.

Pozostałe pola opcjonalne:
- `artykul`: numer przepisu (`23`, `33`, `117^1`), dla bezpośredniego fragmentu jeżeli źródło go wspiera;
- `strona`: 1-based, domyślnie 1; tekst do ok. 5000 znaków na odpowiedź; **paginacja od początku do końca oryginalnego tekstu**, nie od pierwszego snippetu;
- `adres_zrodlowy`: wyłącznie dla źródeł z wewnętrznym identyfikatorem (`sn:`, `edpb:`, `ms:`), po allowliście zaufanych domen i blokadzie SSRF. Nie wolno dopuszczać URL IP, localhost, prywatnych hostów, redirektów poza allowlistę.

Przykłady wejścia:
- `eli:DU/2024/917`, `Dz.U. 2024 poz. 917`, `eli:MP/2026/100`;
- `nsa:389F2C5B67`, `saos:166511`;
- `celex:32016R0679:pl`, `RODO art. 33`;
- `eureka:646788`, `sn:hFvgRJcBZvGrB8P_afyJ`, `edpb:...:pl`, `ms:...`.

Wynik — ustrukturyzowany, np.:
```json
{
  "status": "found",
  "identyfikator": "nsa:389F2C5B67",
  "typ": "orzeczenie",
  "zrodlo": "CBOSA",
  "adres_urzedowy": "https://orzeczenia.nsa.gov.pl/doc/389F2C5B67",
  "tytul": "II SA/Wa 1353/19",
  "dokument_pelny": false,
  "strona": 1,
  "kolejna_strona": 2,
  "dalszy_fragment": true,
  "tekst": "[fragment pełnego orzeczenia, nie snippet wyszukiwania]"
}
```
**Ważne:** pochodzenie, identyfikator, aktualność wersji, zakres rzeczywiście pobranych danych i źródło cytowania są obowiązkowe. `dokument_pelny` musi być ustalone na podstawie metadanych backendu, nigdy domyślnie.

## Macierz rozwiązywania identyfikatorów

| Prefiks/format | Backend | Bezpieczny sposób | Warunek |
|---|---|---|---|
| `eli:DU/2024/917`, `Dz.U. 2024 poz. 917` | Sejm ELI API | `GET https://api.sejm.gov.pl/eli/acts/DU/2024/917` + `/text.html`; HTML tylko gdy `textHTML=true` | Oficjalny akt i datę tekstu sprawdzać w metadanych; nie utożsamiać tekstu jednolitego z najnowszym stanem po zmianach |
| `eli:MP/...` | Sejm ELI API | Identyczna ścieżka dla MP | Obsłużyć brak HTML/PDF-only jawnie |
| `nsa:389F2C5B67` | NSA MCP/CBOSA | `get_judgment(doc_id,offset,limit)` | Natywna paginacja dopiero z PR NSA; stary backend zwraca 2000 znaków i NIE potwierdza kompletności |
| `saos:166511` | SAOS MCP | `get_judgment(id,offset,limit)` | Metadane `totalLength/hasMore/nextOffset`, citacje |
| `celex:32016R0679:pl` / RODO | EUR-Lex | Polski tekst CELEX na żywo, jeśli możliwy z legalnego oficjalnego API; w razie ograniczeń HTML/JS zwrócić adres PL i status `source_unavailable`, nie podstawiać angielskiej treści | Nie opierać pełnego odczytu na angielskim korpusie EU-COMPLIANCE |
| `eureka:646788` | EUREKA MF | Oficjalny adres `https://eureka.mf.gov.pl/informacje/podglad/646788` lub dedykowany connector, jeżeli dostępny | Sprawdzić czy pełna treść jest pobieralna; nie wymyślać wyniku |
| `ms:...` | Portal orzeczeń MS | Oficjalny `orzeczenia.ms.gov.pl/content/$N/...` po sprawdzeniu ID/URL | ID różni się od numerycznego SAOS; nie przekazywać do SAOS |
| `sn:...` | Sąd Najwyższy | ID Repertorium jest **wewnętrzny**, nie jest publicznym ID do pobrania. Wymaga sygnatury/URL i potwierdzenia wyniku w źródle | Nigdy nie budować fikcyjnego URL z opaque ID |
| `edpb:...:pl` | EROD/EDPB | Wiarygodny URL PDF zwrócony przez REPERTORIUM lub oficjalne wyszukiwanie | Dopiero PDF text extraction / weryfikacja licencji; nie udawać, że link jest pobranym tekstem |
| pozostałe `krs:`, `uodo:`, `kio:`, `ecli:` | odpowiednio rejestr, organ, orzeczenia UE | Dodać deterministyczne adaptery i testy z przykładowymi identyfikatorami | Nie deklarować jako funkcjonalnych, dopóki nie są przetestowane |

**Źródło ELI:** https://api.sejm.gov.pl/eli_pl.html i dokumentacja `/text.html` oraz podfragmenty `/art/{art}`. Zweryfikowany akt `DU/2024/917` ma `textHTML=true` i jest dostępny w HTML. EUR-Lex może wymagać dodatkowego, legalnego sposobu dostępu do oficjalnego HTML/XML; zwykłe pobranie zakończyło się kontrolą przeciw botom w teście HTTP.

## Ograniczenie liczby narzędzi i kosztu

- W portalu `lex` pozostawić tylko **REPERTORIUM** i **resolver**. Nie wystawiać modelowi BASIC-MEMORY, NSA, SAOS, USTAWY, KRS itd. przez **ten konkretny portal prawny**. Nadal zachować serwery dla wewnętrznego routingu/diagnostyki i ewentualnie osobne środowisko `ai`.
- Nie instalować nowego monolitu z dziesięcioma toolami UE, nie łączyć baz z repo i nie kopiować kodu Repertorium.
- Resolver ma wykonywać tylko 1 deterministyczne żądanie backendu, a nie automatyczne wyszukiwanie we wszystkich źródłach i wielokrotne retry.
- Zachować funkcje eksperckie (np. citator) jako niewidoczne dla modelu i nie wyłączać ich fizycznie, dopóki potrzeba ich nie zostanie formalnie wykluczona.

## Fazy realizacji i kryteria odbioru

1. Implementować w **osobnym repo/trybie serwera** mikro-MCP z jednym widocznym narzędziem, testować rozpoznawanie ID, status `unsupported`, ELI, SAOS, NSA. Bez ingerencji w `mcp-repertorium`. Nie włączać jednocześnie 5 tooli pełnego wrappera w minimalnym trybie.
2. Dodać CELEX/RODO (urzędowy PL), EUREKA, SN, EDPB, MS dopiero po realnym sprawdzeniu pełnych źródeł; komunikat `link_only` albo `unavailable` jest lepszy od wyprodukowanej treści.
3. Ujednolicić `content` i `structuredContent`, bez podwajania ogromnych bloków i bez utraty cytowań przez Code Mode, testy dużych dokumentów i limit odpowiedzi.
4. Test na NAS i publicznym endpointzie: `DU/2024/917`, `nsa:389F2C5B67`, `saos:166511`, `celex:32016R0679:pl`, `sn:...`, `edpb:...`; walidacja aktualności i pochodzenia, strony 1/2/ostatnia, błąd źródła.
5. Sprawdzić routing Cloudflare i umożliwić rzeczywisty dostęp do REPERTORIUM przez portal; aktualnie `lex` w `portal_list_servers` ma osiem innych serwerów i **nie wylicza REPERTORIUM**, choć kontener na NAS działa.
6. Dopiero po zielonym smoke **wyłączyć widoczność** zbędnych upstream tooli w `lex`, bez usuwania kontenerów, bez nowych polityk per serwer. Rollback: poprzednia lista serwerów, obrazy bez zmian.

## Zakaz zmian

**REPERTORIUM — bez zmian w kodzie, kontenerze, proxy, politykach, wdrożeniu i bazie.** Zmierzone wyłącznie odpowiedzi z istniejącego MCP. Pozostałe kontenery nie zostały przełączone. Nie utożsamiać roboczej specyfikacji z działającym resolverem.


## Aktualizacja 2026-10-31 — LOCAL-FIRST + Webwright MCP

**Ważne: ta sekcja zastępuje wcześniejszy opis bezpośredniego pobierania ELI jako pierwszego kroku.** Dotychczasowy plan był API-first; obecna implementacja ma pierwszeństwo lokalne. Bez zmian w REPERTORIUM.

### USTAWY: rzeczywista baza ma 37 aktów, a nie pełne archiwum Dz.U.

Sprawdzone na uruchomionym MCP USTAWY: istnieje dokładne `DU/2024/917` (`uozp`, 74 artykuły), jak również 36 innych indeksowanych aktów. Działający kontener USTAWY ma **brak bind mountów** — SQLite znajduje się wewnątrz obrazu. Nie wymagać kopiowania DB jako warunku uruchomienia resolvera.

NOWA ścieżka dla `eli:DU/2024/917`:
1. Jeżeli operator dobrowolnie skonfiguruje `PRAWO_USTAWY_SQLITE` read-only, czytaj bezpośrednio po ELI z lokalnego indeksu.
2. W przeciwnym razie wywołaj **lokalny serwer USTAWY** `akt_po_eli(eli,offset,limit,art)` z osobnego draft PR [grounding-prawo #81](https://github.com/elconcept/grounding-prawo/pull/81). Do chwili jego wdrożenia dla konkretnych artykułów możliwe jest użycie dotychczasowych `akty` i `artykul`.
3. Sprawdź trwały cache resolvera `PRAWO_RESOLVER_CACHE` z sumą SHA-256.
4. **Wyłącznie jeżeli powyższe nie pokrywa żądanego tekstu**, zapytaj oficjalne API Sejmu ELI i po prawidłowej odpowiedzi zapisz tekst/metadane/źródło/SHA-256 w trwałym SQLite resolvera.

Uwagi: `akt_po_eli` zwraca wszystkie **zaindeksowane artykuły**, ale nie pełny PDF publikacji (może brakować załączników); `dokument_pelny=false` ma pozostać. Nie utożsamiaj numeru tekstu jednolitego z każdą późniejszą nowelizacją. Nie promuj do pełnego cache samego snippetu ani urwanej strony.

### SAOS / NSA: nie duplikować mirrorów

SAOS ma własny lokalny mirror z mechanizmem oficjalnego API jako fallback. Resolver najpierw wykorzystuje lokalne zapisane fragmenty, a następnie deleguje `get_judgment` do źródłowego MCP. Tylko fragment z metadanymi `offset`, `totalLength`, `returnedLength`, `nextOffset`, `hasMore` może zostać zapisany do trwałej tabeli `fragments` cache resolvera. W razie braku metadanych status `niezweryfikowana_kompletność`; nie przechowuj tego jako pełny wyrok. NSA nie ma potwierdzonego lokalnego mirrora na poziomie SAOS.

### CELEX i ECLI po polsku

1. `PRAWO_EU_PL_SQLITE`: lokalny zbiór **urzędowych polskich tekstów**, format `documents` z flagą `wersja_urzedowa_pl=true`.
2. Lokalny trwały cache `PRAWO_RESOLVER_CACHE`, weryfikacja SHA-256 i flagi oficjalnej wersji PL.
3. CELEX: opcjonalny wewnętrzny `webwright-legal-pl` MCP, uruchamia oryginalny skrypt autora w Playwright, zapisuje pliki i screenshots na NAS. **Wersja dostarczona przez autora pobiera całą stronę (również menu), a nie zweryfikowany tekst aktu, więc wynik ma status `kandydat_zapisany`, a nie pełen dokument.** Odrębny walidator urzędowego PDF/XML i utworzenie polskiego korpusu są blokującymi zadaniami P0.
4. ECLI: jeżeli brak tekstu lokalnego, istniejący EU-SPARQL służy wyłącznie do odszukania metadanych/cytowań, które zapisujemy jako kandydata. **Pełny tekst ECLI PL jeszcze nie jest automatycznie materializowany** — nie podstawiać angielskiego korpusu.
5. Nie traktować linku `/EN/TXT/` w wyniku Repertorium dla `celex:...:pl` jako źródła PL. Konstruować i następnie weryfikować `/PL/TXT/`.

### Webwright: faktyczny zakres i bezpieczeństwo

Dostarczony ZIP jest **skillem** z dwoma skryptami, nie gotowym serwerem MCP. Skrypty skopiowano z `matematicsolutions/awesome-matematic-skills-pl` rewizja `e99b534` do `vendor/webwright_legal_pl` wraz z licencją Apache-2.0; porównano skład z załączonym ZIP.

Nowy `webwright_internal.py` udostępnia **wyłącznie w sieci prywatnej kontenerów** dwa narzędzia: `fetch_celex_pl` i `fetch_orzeczenie_po_sygnaturze`. Router modelowi ich nie wystawia. Uruchamia tylko dwie stałe komendy (bez `shell=True`), ogranicza czas, współbieżność i długość wejścia, zapisuje metadane/screeny. SN: wyniki z przeglądarki są **kandydatem**, dopóki nie pobrano/zweryfikowano pełnego PDF. **MS i TK nie są zaimplementowane** w oryginalnym skrypcie ani w aktualnym adapterze. Ich wdrożenie wymaga selektorów, testów integracyjnych i weryfikacji pełnych tekstów. Nie omijać CAPTCHA/WAF ani ograniczeń dostępu.

Nowe pliki: `src/prawo_pl_mcp/{local_corpus.py,browser_bridge.py,webwright_internal.py,webwright_asgi.py}`, `vendor/webwright_legal_pl`, `deploy/minimal-legal/compose.staging.yaml` i `tests/test_local_corpus.py`. Brak wdrożenia na NAS. Staging resolver HTTP ma jeden tool `pobierz_dokument`; drugi widoczny tool to istniejące REPERTORIUM, które pozostaje niezmienione.

### Zweryfikowane testy przed etapem staging

- **Przeprowadzono** przez kontener Python na danych tymczasowych: odczyt USTAWY po dokładnym ELI, niezamienianie roczników, cache z SHA-256, fragmenty SAOS i candidate cache. PASS.
- **Przeprowadzono** przez kontener Python: nowy `Baza.akt_po_eli` — dokładne ELI, offset/limit, out-of-scope, brak przypisywania pełnego urzędowego dokumentu. PASS.
- **Nie przeprowadzono jeszcze** pełnego pytest, budowy obu nowych obrazów, próby browser w oficjalnych domenach ani próby MCP end-to-end przez Cloudflare. Traktować oba PR jako draft.

### Odbiór

Przed ukryciem narzędzi w `lex`: USTAWY #81 wdrożone jako źródło wewnętrzne; działający resolver z trwałym cache; walidacja braku wywołań API Sejmu przy trafieniach lokalnych; próby cache hit po restarcie; czytelne sygnały niekompletności; browser fallback SN oraz CELEX/PL sprawdzone na znanych dokumentach; później dopiero adaptery MS i TK. REPERTORIUM cały czas nietknięte.
