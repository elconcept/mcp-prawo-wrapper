# Plan decyzyjny i zasady zmian — MCP-PRAWO (8 listopada 2026)

**STATUS: DO AKCEPTACJI. ŻADNE PRACE WDROŻENIOWE NIE SĄ UPOWAŻNIONE.**  
**Właściciel decyzji:** użytkownik.  
**Zasięg:** elconcept/mcp-prawo-wrapper, odrębny upstream matematicsolutions/prawo-pl-mcp, istniejące serwery UODO, SAOS, NSA, SPARQL, PMI, Repertorium, PostgreSQL oraz portal Lex.

## ZASADA TRWAŁA: najpierw plan, później akceptacja, na końcu działanie

1. Każda zmiana plików źródłowych, testów, narzędzi, zależności, konfiguracji, stacków Portainera, Cloudflare, poświadczeń, baz danych, ścieżek routingu i sposobu uruchamiania wymaga **wcześniejszego planu zapisanego do pliku .md**.
2. Plan musi rozdzielać stan aktualny, dowody, ocenę wariantów, decyzje do podjęcia, dokładny zakres zmian, testy, skutki uboczne, ryzyka, sposób ograniczenia przestoju i sposób wycofania awarii. Wymagane jest także wykazanie, co pozostanie niezmienione.
3. **Dopiero wyraźna akceptacja użytkownika** zakresu planu uprawnia do działania. Samo polecenie zbadania problemu, udzielenia wyjaśnienia czy sporządzenia raportu nie oznacza zgody na wdrożenie. Milczenie i brak sprzeciwu nie są zgodą.
4. Niedopuszczalne są samowolne refaktoryzacje, zastępowanie oryginalnej architektury inną, automatyczne rollbacki, podmiana kontenerów, zmiana tokenów i usuwanie źródeł portalu w toku audytu.
5. Gdy nowy problem ujawni się w czasie realizacji zatwierdzonego planu i wymaga przekroczenia zakresu, należy przerwać tę część wdrożenia i przedstawić nowy plan/zmianę planu do akceptacji.
6. Pomiędzy zatwierdzeniem planu a produkcyjnym przełączeniem musi istnieć dowód testów kontraktowych i smoke end-to-end. Nie wolno utożsamiać healthy/TCP z działaniem przez portal.
7. Sama dokumentacja audytu i tego planu może być utrwalona **na osobnej gałęzi dokumentacyjnej** bez ingerencji w main, produkcję i CI/deploy. To jedyny zakres zapisu autoryzowany bieżącym poleceniem.

## 1. Cel i granice

Celem przyszłych prac — wyłącznie po zatwierdzeniu — jest zachowanie skutecznych rozszerzeń (HTTP do już istniejących serwerów, free Repertorium, PMI, cache pełnych tekstów, paginacja, pięć narzędzi), przy jednoczesnym wyeliminowaniu zmian semantycznych i regresji niezaakceptowanych przez użytkownika. Oryginalny upstream ma pozostać odniesieniem o weryfikowalnej wersji i niezmienionym kodzie, chyba że użytkownik jawnie wybierze wariant wersjonowanych patchy.

NIE jest celem tego dokumentu: rollback do 15 października, automatyczna zamiana HTTP na uvx, usunięcie Repertorium/Tor, usunięcie kontenerów, przełączenie Lex, zmiana poświadczeń, czyszczenie PostgreSQL, przepisanie aplikacji czy instalowanie nowych usług.

## 2. Wymagane decyzje PRZED rozpoczęciem implementacji

| ID | Pytanie | Warianty do oceny |
|---|---|---|
| D01 | Co oznacza nienaruszalność upstream w finalnej architekturze? | A: dosłownie upstream bez zmian + overlay; B: pin upstream i jawne patch-sety zatwierdzone przez użytkownika |
| D02 | Jak zachować obsługę istniejących serwerów MCP? | HTTP proxy w warstwie adaptera; patch transportu w forku, świadomie zaakceptowany; nie wracać do uvx przez domysł |
| D03 | Czy zachować domyślne pl_search = Repertorium? | Wymagane source jak upstream; opcjonalny parametr z wersjonowanym kontraktem; nowy osobny alias |
| D04 | Co zrobić z EUREKA, ustawy, eu-compliance, legalize? | Zachować komplet katalogu z możliwością wyłączenia wdrożeniowego; odrębna polityka aktywnych źródeł; zaakceptować dotychczasowe ograniczenie |
| D05 | Jak ma działać cache? | Off dla prawnie wrażliwych zapytań; on-demand z pełnym kluczem kontekstu i TTL; opt-in z explicit refresh |
| D06 | Które odpowiedzi są kanoniczne? | Oficjalny ELI i SAOS/CBOSA jako treść źródłowa; PMI jako odkrywanie/kopia pomocnicza, zawsze z URL i datą |
| D07 | Jak traktować wyszukiwanie wielu baz? | Jedno źródło jak upstream; nowe oddzielne narzędzie federacyjne z jawną listą źródeł i statusami częściowymi |
| D08 | Jaki jest próg akceptacji wdrożenia Lex? | Wymagana odpowiedź tools/list przez HTTPS i poprawne wywołanie pl_search bez wyłączania Access |

Brak wyboru D01–D08 oznacza brak autoryzacji implementacji.

## 3. Fazy możliwe dopiero po akceptacji

### Faza P0 — zamrożenie referencji, bez ingerencji w dane

- Potwierdzić SHA upstream i forka oraz diff; utworzyć odtwarzalny snapshot kodu i manifestów środowiska, zachowując sekrety poza repo.
- Spisać listę rzeczywiście wystawionych źródeł i narzędzi, ich nazwy, wersje, endpointy i statusy, bez zmiany reguł Lex.
- Odnotować schemat PostgreSQL, aktualną politykę TTL, sposób backupu i identyfikatory kontenerów.
- Kryterium: odczyty audytowe i kompletny ślad wersji. Żadnych restartów ani zmian rutingu.

### Faza P1 — kontrakty i testy izolowane

- Uruchomić testy na odseparowanej kopii/staging, nie na aktywnych kontenerach. Oddzielić testy offline od smoke/HTTP.
- Zweryfikować diff deskryptorów pięciu narzędzi z tests/tools.lock.json oraz parametry wymagane, nazwy, kody błędów, formaty odpowiedzi, paginację i source_id.
- Fixture: SAOS I Ca 510/20, NSA III OSK 533/24, UODO DKN.5131.27.2022, EU-SPARQL CELEX 32016R0679, PMI akt/art. 23, ISAP akt z natywnym search_text.
- Przetestować cache miss/hit, różne extra dla tego samego dokumentu, refresh, wygasanie, skrócony tekst, nieznany identyfikator, wiele wyników UODO, błąd upstream oraz timeout.
- Porównać hash tekstu, metadane i URL między natywnym MCP a wrapperem. Świadomie dopuszczone transformacje opisać.
- Kryterium: raport pass/fail z konkretną listą zachowań regresyjnych; żadnego niejawnego prefetch podczas testów offline.

### Faza P2 — przegląd architektury i szczegółowy ADR

- Sporządzić ADR wariantów: niezmieniony upstream plus warstwa HTTP/routing/cache versus jawny zestaw patchy z przywróconym procesem ich akceptacji.
- Obliczyć koszty obsługi aktualizacji upstream, degradacji źródła, utraty autoryzacji i cache.
- Zaprojektować korekty punktowe A01–A14 z [raportu](../docs/AUDYT_mcp_prawo_upstream_i_regresje_20261108.md), bez naruszenia potrzebnego HTTP.
- Pokazać użytkownikowi proponowany diff plik po pliku oraz testy. **To osobny punkt akceptacji zakresu zmian.**

### Faza P3 — implementacja po wyraźnej zgodzie

- Wszystkie patche wyłącznie na dedykowanej gałęzi roboczej; PR z opisem diff upstream, wpływu na API i wyjątków.
- Osobne zestawy: transport/registry, cache/routing, PMI, dane/metadata, instrukcje/coverage, deploy. Nie łączyć niepowiązanych zmian w jednym commicie.
- Bez zmian Repertorium i jego Tor; kontenery źródłowe mają zostać niezależne.
- CI i testy E2E staging muszą przejść; data fixture i źródło tekstu obowiązkowe.

### Faza P4 — wdrożenie wyłącznie po odrębnej akceptacji produkcyjnej

- Dokładny plan kolejności stacków i routingu, snapshot, konfiguracja service auth, próg sukcesu, monitorowanie i sposób przywrócenia poprzedniej usługi przy awarii.
- Przed usunięciem jakiejkolwiek mapy Lex: przez HTTPS/Cloudflare Access sprawdzić initialize, tools/list (wszystkie 5), pl_list_sources, pl_search/pl_call do źródeł i pełny pl_get_document.
- Gdy upstream zwraca stronę Access HTML zamiast MCP lub tool count = 0: wdrożenie zostaje zatrzymane, bez usuwania źródeł; nie oznaczać „healthy” jako równoważnego „działa”.
- Utrzymanie rollback jako planu awaryjnego NIE oznacza upoważnienia do jego wykonania bez uzgodnionych warunków.

## 4. Minimalne kryteria akceptacji technicznej

1. Pięć oryginalnych narzędzi zachowuje udokumentowany, zatwierdzony kontrakt lub jest wersjonowane wraz z jawną decyzją o zmianie.
2. Upstream jest odtwarzalny z dokładnego SHA, wszystkie modyfikacje warstwy własnej są oddzielne lub indywidualnie zatwierdzone.
3. HTTP do istniejących MCP działa i nie wymusza instalacji uvx/npx w NAS.
4. UODO, EU-SPARQL, NSA, SAOS, PMI, Repertorium odpowiadają poprzez wrapper na zestawie golden fixtures.
5. Nie dochodzi do podmiany tekstu przez błędny cache_key, a źródło, wersja, świeżość i kompletność są wyrażone prawidłowo.
6. Wywołanie ISAP z page i extra zachowuje uzgodnioną semantykę natywną lub nową wersjonowaną, bez milczącego odrzucenia parametrów.
7. pl_coverage i instrukcje odzwierciedlają realne źródła live oraz snapshoty/cache.
8. Lex korzysta z wrappera przez Cloudflare Access bez osłabienia ochrony; brak statusu error.
9. Testy nie uruchamiają ukrytych pobrań ani zapisów do produkcyjnych baz.
10. Dokumentacja, changelog i checklisty operacyjne są kompletne przed wdrożeniem.

## 5. Czynności dopuszczone TERAZ

Wyłącznie odczyt repozytoriów i dokumentacji, analiza istniejących logów/konfiguracji bez modyfikacji, redakcja raportu oraz zapis tego planu na **osobnej gałęzi dokumentacyjnej**. Brak merge, PR, tagów wydania, zmian main, kodu, kontenerów, bazy, CI, Cloudflare i poświadczeń.

## 6. Akceptacja

Plan pozostaje w statusie **NIEZATWIERDZONY**, dopóki użytkownik nie złoży jednoznacznej dyspozycji akceptującej konkretny wariant i etap prac. Zgoda na audyt albo na zapis tego pliku nie jest zgodą na implementację. Wszelkie zakresy wykraczające poza akceptowany plan wymagają ponownego zatwierdzenia.
