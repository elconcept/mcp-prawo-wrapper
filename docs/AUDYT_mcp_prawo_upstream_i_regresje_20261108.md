# Audyt architektury forka mcp-prawo-wrapper — 8 listopada 2026

**Status:** dokumentacja audytowa, bez wdrożenia i bez rollbacku.  
**Zakres porównania:** matematicsolutions/prawo-pl-mcp, wspólny przodek 6c7bae4e41d4bf54d5074dece2a0f3d13fcf235a, względem elconcept/mcp-prawo-wrapper, HEAD f192d13f2bc5a92f2191740ad744a2e29a17b2ce.  
**Metoda:** read-only GitHub compare, historia commitów, źródła i testy w repozytorium, wcześniej udokumentowane testy bezpośrednich MCP, odczyt konfiguracji i statusu portalu. Nie wykonywano zmian w aplikacjach, kontenerach, portalu ani bazie w ramach tego audytu.

## 1. Konkluzja

Rozwiązanie NIE zastąpiło całego silnika upstream: zachowano pięć narzędzi (pl_coverage, pl_list_sources, pl_search, pl_get_document i pl_call), rozpoznawanie parametrów, obsługę stron, podstawowe logowanie i mechanizm proxy MCP. Jednocześnie zmieniono kluczową logikę wykonywania i kontrakt jednej z funkcji. Oryginalny kod nie pozostał nienaruszalny. Nie można sprowadzić zmian do instalacji istniejących konektorów.

Nie należy automatycznie kwalifikować wszystkich zmian jako wadliwych: zdalny transport Streamable HTTP do istniejących kontenerów był uzasadniony architektonicznie, a testy bezpośrednie potwierdziły komunikację UODO, EU-SPARQL, NSA, SAOS i PMI. Z drugiej strony kontrakt, testy i dokumentacja nie zostały dostosowane w sposób zapewniający porównywalną kontrolę regresji. Udokumentowano również problemy semantyczne w ścieżkach pełnego tekstu.

**Zakaz zmian:** żadne poprawki, migracje ani rollback nie są elementem tego raportu. Każde przyszłe wykonanie wymaga wcześniejszego planu i wyraźnej akceptacji użytkownika.

## 2. Historia i właściwe przypisanie zmian

| Data UTC | Commit | Zmiana | Ocena pochodzenia |
|---|---|---|---|
| 2026-10-15 | 6c7bae4 | Punkt wspólny z matematicsolutions/main | Referencyjna wersja upstream |
| 2026-10-22 | 15a4245 | Obsługa istniejących serwerów MCP przez Streamable HTTP, filtr źródeł, zamiana eureka na ustawy | Osobny, scalony PR #2; NIE jest zmianą z prac nad PMI 8 listopada |
| 2026-10-30 | 83ed11f | Plan audytu integracji portalu Lex | Tylko dokument |
| 2026-11-08 00:18 | 5d7560f | Repertorium, automatyczna interpretacja identyfikatorów, lokalny SAOS SQLite, Sejm PDF, PostgreSQL, prefetch, zmieniony pl_get_document i domyślne pl_search | Największa zmiana semantyczna w rdzeniu |
| 2026-11-08 13:04 | 9432d55 | Dodatkowy serwis PMI HTML i jego integracja z registry/local_docs/server | Rozszerzenie rejestru i ścieżki dokumentów |
| 2026-11-08 15:56 | 9a9391f | Przemianowanie serwisu na pmi, aktualizacja konfiguracji | W dużej części zmiana organizacyjna |
| 2026-11-08 19:25 | f192d13 | Włączenie zewnętrznego EU-SPARQL w compose NAS | Zmiana konfiguracji źródeł, bez zmiany rdzenia Pythona |

Upstream i fork różnią się w 19 ścieżkach: 6 zmodyfikowanych istniejących plików i 13 plików dodanych. Wśród zmodyfikowanych są krytyczne server.py, registry.py i pool.py. **Poprzednie ogólne przypisanie usunięcia EUREKA pracom z 8 listopada było nieścisłe.** Commit 15a4245 pochodzi z osobnego PR #2, otwartego 20 października i scalonego 22 października. Sam fakt scalenia PR nie przesądza o akceptacji wszystkich późniejszych zmian.

Źródła:
- [Porównanie forka z upstream](https://github.com/elconcept/mcp-prawo-wrapper/compare/6c7bae4e41d4bf54d5074dece2a0f3d13fcf235a...f192d13f2bc5a92f2191740ad744a2e29a17b2ce)
- [PR #2 z października](https://github.com/elconcept/mcp-prawo-wrapper/pull/2)
- [Commit 5d7560f — routing i cache](https://github.com/elconcept/mcp-prawo-wrapper/commit/5d7560f006f7996a2dffb80be8072849d9da8253)
- [Commit 9432d55 — PMI](https://github.com/elconcept/mcp-prawo-wrapper/commit/9432d55403fac48aec17e0f9c070d39958a4e123)

## 3. Jak faktycznie działa wrapper

To federacyjny broker MCP z pięcioma narzędziami publicznymi, nie wyszukiwarka, która automatycznie odpytuje wszystkie bazy.

1. pl_list_sources bez argumentów czyta lokalny katalog; z source_id odpytuje tools/list wskazanego konektora.
2. pl_search wybiera **jedno** źródło określone parametrem source, mapuje argumenty do narzędzia natywnego, zwraca jego wynik. Od 5d7560f brak parametru source oznacza Repertorium.
3. pl_call kieruje wywołanie do **jednego** serwera i jednego narzędzia, z walidacją jego schematu.
4. pl_get_document może zwrócić dane z PostgreSQL, SAOS SQLite, pliku PDF Sejmu lub z natywnego MCP, zależnie od identyfikatora i dostępności. W tym narzędziu występuje nowa logika domenowa.
5. pl_coverage deklaruje pokrycie, ale jego treść pozostała napisana dla cienkiego proxy bez lokalnego cache.

Nie ma fan-out, agregacji odpowiedzi wszystkich źródeł, rankingu między bazami ani automatycznej deduplikacji. Wyjątek od reguły jednego źródła: pl_search(Repertorium) tworzy dodatkowe zadanie prefetch najwyżej trzech identyfikatorów, które może następnie pobrać dokumenty z innych MCP i zapisać je do PostgreSQL. Prefetch nie jest dołączany do odpowiedzi wyszukiwania.

## 4. Wartościowe rozszerzenia — zachować do niezależnej oceny

- **Zdalny transport HTTP:** pool.py wykorzystuje URL wskazany przez PRAWO_PL_MCP_URL_<ID>, a dla pozostałych źródeł zachowuje StdioTransport i podprocesy. Odsyłanie do już uruchomionych kontenerów zamiast tworzenia kolejnych procesów jest spójne z wyrażonym wymaganiem użytkownika.
- **Jeden publiczny kontrakt:** pl_list_sources, pl_search, pl_get_document, pl_call i pl_coverage nadal istnieją. Paginator z upstream pozostaje praktycznie niezmieniony.
- **On-demand full text:** lokalne SQLite SAOS i oficjalny PDF ELI mogą ograniczać zależność od niesprawnych upstreamów; PostgreSQL przyspiesza ponowne pobieranie tych samych dokumentów.
- **PMI:** wyodrębniony kontener zapewnia bezpłatny odczyt publicznych HTML PrawMi (orzeczenie, akt, artykuł) i rozróżnia tekst przepisu od sekcji analizy serwisu.
- **Repertorium:** niezależny backend wyszukiwania semantycznego po polskich źródłach; żaden element audytu nie uzasadnia jego usuwania ani zmian Tor.
- **Zwierzone połączenia:** wcześniejsze testy operacyjne potwierdziły przez pl_call decyzję UODO DKN.5131.27.2022, CELEX 32016R0679, pełne orzeczenie NSA III OSK 533/24 i SAOS I Ca 510/20. To weryfikuje poszczególne drogi, ale nie wszystkie kombinacje i błędy.

Zachowanie tych zalet nie wymaga automatycznej akceptacji zmian rdzenia; sposób ich utrzymania to osobna decyzja architektoniczna.

## 5. Ustalenia wymagające decyzji lub testów

### A01 — kontrakt pl_search: potwierdzona zmiana niezgodna z deskryptorem [wysoki]

W server.py source zmienił się z parametru wymaganego na opcjonalny z domyślną wartością repertorium. tests/tools.lock.json nadal wymaga source. Test test_descriptor_lock.py ma wykrywać dokładnie taki drift. Nie zaktualizowano locka ani wersji pakietu 0.2.4. To udowodniona zmiana schematu, nie dowód, że każdy klient przestał działać.

### A02 — pl_get_document: niezgodność semantyki ISAP [wysoki, statycznie stwierdzony]

Upstream wysyłał identyfikator ELI i parametr page do natywnego get_act_text; obsługiwał także source-specific extra (np. search_text dla artykułu). Obecna implementacja przed natywnym MCP próbuje pobrać cały PDF z Sejmu i odczytać jego tekst, a następnie stosuje lokalną paginację. Gdy PDF zostanie odczytany albo dokument jest w cache, parametry extra i natywna paginacja mogą być pominięte. Opisy registry.py nadal sugerują natywne wyszukanie artykułu. Potrzebne testy porównujące dokładne brzmienie przepisu, wersję aktu, page i search_text.

### A03 — klucz cache nie obejmuje parametrów semantycznych [wysoki, statycznie stwierdzony]

local_docs.cache_id składa się wyłącznie z source i document_id. Nie obejmuje extra, języka, typu wypisu, wersji aktu, daty stanu prawnego ani sposobu pobrania. Pl_get_document odczytuje cache przed walidacją required_extra i przed wywołaniem źródła. W konsekwencji ponowne wywołanie z innymi parametrami może otrzymać poprzednią treść zamiast nowej. To konkretna wada reprezentowania różnych żądań tym samym kluczem. Nie ma dowodu, że już wywołała błędną odpowiedź w konkretnej sprawie.

### A04 — świeżość, integralność i complete [wysoki dla zastosowań prawnych]

PostgreSQL jest cache bez wykazanej w tym repo polityki TTL lub automatycznej rewalidacji; refresh jest opcjonalny. Funkcja looks_truncated rozpoznaje tylko dwa literalne komunikaty o skróceniu. Pole complete w odpowiedzi oznacza w praktyce brak tych fragmentów, a NIE niezależne sprawdzenie kompletności wobec oryginału. Brakuje automatycznej informacji o dacie źródła, wersji aktu, sumie kontrolnej i dacie pozyskania w samej odpowiedzi.

### A05 — rozbieżność deklaracji pokrycia, ADR i zachowania [średni/wysoki]

coverage.py/INSTRUCTIONS/README/ADR 0001 deklarują cienkie proxy bez lokalnego korpusu i cache oraz pobieranie danych na żywo. Implementacja ma lokalny dump SQLite, PDF oraz PostgreSQL. pl_coverage nie odróżnia już live od cache, nie deklaruje jego daty i pochodzenia; model może dostać błędną informację o świeżości i kompletności.

### A06 — prefetch niejawny i asynchroniczny [średni]

pl_search(Repertorium) wywołuje asyncio.create_task(_prefetch_repertorium_hits). W tle może odpalić do trzech wywołań i zapisów PostgreSQL; błędy są przemilczane. Wyszukiwanie pozornie tylko do odczytu ma skutki uboczne w lokalnej bazie. Prefetch nie obejmuje identyfikatorów NSA/ELI, a lista wybieranych wyników wynika z regexu i kolejności tekstu. Bez testu obciążenia i logów nie ma podstaw twierdzić, że przyspieszenie przeważa koszt.

### A07 — rozpoznawanie UODO [średni]

URN może zostać zamieniony na sygnaturę i użyty w uodo_search_decisions. resolve_uodo_id pobiera **pierwszy** identyfikator PublicDocument z odpowiedzi, nie walidując wprost zgodności sygnatury każdego trafienia. Odpowiedź o wielu pasujących dokumentach wymaga testu, aby uniknąć błędnego podstawienia.

### A08 — zakres aktywnych źródeł i utrata części pierwotnej oferty [średni]

Registry ma obecnie 12 deklaracji: saos, nsa, isap, krs, ustawy, kio, uodo, eu-sparql, eu-compliance, legalize, pmi, repertorium. Compose NAS aktywuje **9**: repertorium, saos, nsa, isap, krs, kio, uodo, pmi, eu-sparql. Nie aktywuje ustawy, eu-compliance ani legalize. Pierwotna eureka nie figuruje już w registry po PR #2. To nie oznacza usunięcia osobnych serwerów z NAS, lecz ograniczenie funkcji udostępnianych **przez wrapper**. Należy świadomie zatwierdzić listę źródeł i kompatybilność.

### A09 — testy nie odzwierciedlają nowej architektury [wysoki]

test_dispatch.py pochodzi z założenia, że pl_get_document używa mockowanego POOL. Obecnie wywołuje też PostgreSQL, lokalny SQLite i dla ISAP może wykonywać rzeczywisty HTTP PDF. Test, który wcześniej był offline, może więc zależeć od dostępności zewnętrznej strony albo danych cache. test_local_docs.py zawiera tylko pięć prostych testów, nie obejmuje TTL, kolizji extra, niepełnego tekstu, błędów PDF, uprawnień, stronicowania natywnego czy samego połączenia HTTP. Z repo GitHub Actions nie uzyskano potwierdzenia bieżących wyników CI; nie należy stwierdzać, że cała suita przechodzi.

### A10 — PMI: limity funkcjonalne i kompletność [średni]

PMI opiera się na selektorach HTML konkretnego układu prawmi.pl. Zmiana layoutu może przerwać odczyt. pmi_search rozwiązuje znane sygnatury oraz katalog tytułów ustaw, nie prowadzi semantycznego wyszukiwania orzeczeń. pmi_list_acts bez query zwraca maksymalnie 100 z indeksu 895, bez stronicowania — nie jest więc pełnym API katalogowym. pmi_get_article raportuje total_chars obliczone dla samego body, choć content_text zawiera dodatkowy nagłówek Art. X; to drobna niespójność metadanych. Tekst ze strony prywatnego agregatora nie może być automatycznie utożsamiany z urzędowym tekstem jednolitym na daną datę.

### A11 — utrata metadanych i formatowania w pl_get_document [średni]

text_from_connector wyciąga samo content_text dla PMI/KIO; pozostałe pola odpowiedzi natywnego serwera mogą zostać utracone (w PMI adres źródła jest częściowo odtwarzany). SAOS HTML jest przekształcany do tekstu, PDF do ekstrakcji tekstowej, co może utracić tabelaryczne i inne istotne elementy. pl_call pozostaje drogą do surowego wyniku natywnego konektora. Konieczna jest weryfikacja, które metadane prawne powinny przetrwać ujednolicenie.

### A12 — HTTP i odporność [średni]

Rozszerzenie pool.py pozwala używać istniejących serwerów (pożądane). Przy skonfigurowanym URL niedostępność remote skutkuje source_unavailable, bez automatycznego fallbacku do uvx/npx. Może to być właściwa strategia fail-closed, ale trzeba ją jawnie uzgodnić. Po utracie połączenia klient jest odtwarzany; nie udokumentowano tu testów reconnect i ponownej walidacji narzędzi.

### A13 — wdrożenie i dostępność Lex [wysoki operacyjnie]

Kontener mcp-prawo-wrapper działał lokalnie zdrowo, a jednak Cloudflare MCP Server mcp-prawo ma status error, zero narzędzi; negocjacja protokołu zwraca text/html zamiast MCP. Powodem zarejestrowanym w Cloudflare jest przechwycenie przez Access. W Lex usunięto już bezpośrednie mapowania uodo, eu-sparql, nsa i saos, **przed skutecznym uruchomieniem wrappera w portalu**. Osobne serwery zostały zachowane w Cloudflare i na NAS, ale istnieje luka funkcjonalna dla klientów Lex. Wymaga osobnego zaakceptowanego planu naprawy autoryzacji, bez wyłączania Access.

### A14 — reprodukowalność i kontrola zmian [wysoki procesowo]

Kod głównych funkcji zmieniono na main bez porównywalnego pakietu testów regresyjnych i bez uaktualnienia tools.lock.json oraz wersji 0.2.4. Schemat lokalnej bazy PostgreSQL, zasady utrzymania indeksów/retencji i awaryjnego odtworzenia nie są w tym forku udokumentowane jako migracje. Samo TCP w healthcheck wrappera nie weryfikuje rzeczywistego tools/list i nie ujawnia błędu Access, którego doświadczył Lex. Najważniejsze: brak bramki akceptacyjnej użytkownika przed zmianą rdzenia i konfiguracji.

## 6. Czego nie należy przedstawiać jako ustalone

- Nie wykazano, że cały kod upstream został usunięty lub że wszystkie obecne modyfikacje są wadliwe.
- Nie wykazano jeszcze błędu merytorycznego w konkretnej odpowiedzi cache; wykazano mechanizm, który może go spowodować.
- Nie dowiedziono przejścia całej aktualnej suity CI; nie uruchamiano jej w ramach tego audytu.
- Nie przeprowadzono pełnych testów obciążenia, jakości ekstrakcji PDF/HTML, historycznego stanu prawnego ani poprawnego odnowienia sesji MCP.
- Nie oceniano potrzeby usuwania działających kontenerów. Repertorium i jego Tor są poza zakresem zmian.
- PR #2 jest osobnym udokumentowanym etapem; jego pochodzenia nie wolno mieszać z bezpośrednimi zmianami 8 listopada.

## 7. Ocena architektury i warianty

**Wariant 1 — utrzymanie obecnego forka:** najniższy koszt wdrożeniowy, zachowuje działające funkcje, ale wymaga uznania formalnych wyjątków od nienaruszalności upstream, zamknięcia luk testowych i naprawy semantyki kontraktu. Nie spełnia dosłownie reguły nienaruszalnego kodu bazowego.

**Wariant 2 — upstream w niezmienionej postaci plus warstwa kompatybilności:** rozdziela kod referencyjny od adapterów HTTP, Repertorium, PMI, cache i źródeł specjalnych. Najlepiej spełnia zasadę nienaruszalności, ale wymaga dodatkowych testów kontraktowych i planu przełączenia, by nie stracić obecnej funkcjonalności. NIE jest synonimem rollbacku ani odrzucenia rozszerzeń.

**Wariant 3 — wersjonowany fork z jawnie zaakceptowanymi patchami:** akceptuje wyjątkowe ingerencje, pin bazowego upstream, zestaw ustrukturyzowanych patchy, ADR i testy. Mniej zmian niż wariant 2, ale nadal zmienia kod bazowy.

Żaden wariant nie został wybrany ani wdrożony. Kryteria decyzji: zgodność z niezmiennym upstream, pełna treść i źródło, zgodność pięciu narzędzi, transport HTTP, zachowanie aktualnych źródeł, koszt utrzymania i możliwość aktualizacji wersji upstream.

## 8. Materiał do planu

Osobny dokument _PLAN/20261108_plan_zatwierdzenia_architektury_mcp_prawo.md zawiera bramki akceptacji, kolejność prac, warianty bez automatycznego wyboru, testy i warunki wdrożenia.

**Obecny status:** wyłącznie raport. Bez zmian implementacji i infrastruktury; żadna faza planu nie jest autoryzowana.
