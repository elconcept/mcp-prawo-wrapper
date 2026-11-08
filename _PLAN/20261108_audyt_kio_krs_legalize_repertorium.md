# Plan i raport kontrolny: KIO, KRS, Legalize, Repertorium i własność plików (2026-11-08)

**Status: audyt zakończony; prace rozszerzające zakres wymagają nowej akceptacji.**
**Repozytorium:** elconcept/mcp-prawo-wrapper. Dokument tylko na gałęzi audit/upstream-preservation-20261108, nie na main.

## 1. Zlecony i wykonany zakres

| Czynność | Status | Dowód |
|---|---|---|
| Sprawdzenie UID/GID wrappera | wykonane | Docker Config.User = 1029:100, proces /app poprzednio 1029:100 |
| chown /app w działającym kontenerze | wykonane | root exec chown -R 1029:100 /app, 16 pozycji, 0 niezgodności |
| chown katalogu repo na NAS | wykonane | oddzielny kontener z bind mountem, exit=0; /volume2/docker/mcp-prawo-wrapper 1029:100 |
| Wykluczenie tokenów z Git | wykonane lokalnie i w gałęzi audytowej | wpisy .cf-service-token oraz .secrets/ w .gitignore; 0644 i 1029:100 lokalnie |
| Kopia poświadczeń Explorera | NIE WYKONANO | Operacja obejmująca poświadczenia została zablokowana przez zabezpieczenia; bez alternatywnych prób obejścia |
| KIO | wykonane: audyt połączenia | mcp-kio running/healthy, 1029:100; przez wrapper tools/list 6; pl_call(kio_recent) zwróciło KIO 4385/26 |
| KRS | wykonane: audyt połączenia | mcp-krs running/healthy, 1029:100; tools/list 3; pl_call(get_entity) odczytało KRS 0000028860 |
| Cloudflare KRS | potwierdzone | zdrowy ds1821 z krs.xlap.pl -> http://mcp-krs:8000, MCP status ready, 3 tools |
| Cloudflare KIO | brak routingu | żadna z konfiguracji czterech tuneli nie zawiera reguły dla KIO, w MCP Servers brak wpisu KIO |
| Repertorium default | zweryfikowany kod i tools/list | source optional z default repertorium; pl_search.required=[]; upstream source required |
| Legalize vs ISAP | przeanalizowano | źródła autorów i aktualne repozytoria GitHub |

**Istotny limit trwałości:** chown /app działa w bieżącym kontenerze. Dockerfile.nas nadal nie ma COPY --chown, więc odtworzenie obrazu przywróci właściciela plików obrazu do root. Nie rekonfigurowano obrazu ani nie restartowano stacka.

## 2. KIO/KRS — sieć i dostęp

Oba MCP są w cf_mcp_krs, zaś wrapper do tej sieci należy. W komponencie wrappera aktywny jest PRAWO_PL_MCP_URL_KIO=http://mcp-kio:8000/mcp i PRAWO_PL_MCP_URL_KRS=http://mcp-krs:8000/mcp; oba źródła na allowlist PRAWO_PL_MCP_SOURCES. Testy realnych tool calls pomyślne.

KIO nie ma publicznej konfiguracji tunelu. Nie należy wywodzić publicznej dostępności z tego, że kontener i wewnętrzne MCP działają. Publiczną regułę można dodać tylko po osobnym zatwierdzeniu planu bezpieczeństwa, hostname, Access policy i testów.

## 3. Legalize a ISAP

**mcp-isap (matematicsolutions):** polskie DU/MP z Sejm ELI API, 96k+ ogłaszanych aktów, wyszukiwanie po tytule/roku/typie/statusie, get_act (metadane i stan), get_act_text (stronice 5000 znaków i search_text, oznaczenie wersji tekstu). Źródło państwowe, dane live, bez GitHub tokena.

**legalize-mcp (matematicsolutions, NIE oficjalny legalize-dev/mcp):** read-only GitHub legalize-dev, deklarowane 32 jurysdykcje w tym 21 UE; legalize_list_countries, legalize_search_laws (wymaga GITHUB_TOKEN), legalize_get_meta, legalize_get_law (opcja sha dla historycznej wersji), legalize_list_reforms (lista commitów reform), legalize_coverage. Zapewnia porównania międzynarodowe oraz odnajdywanie historycznych wersji i audytowalny SHA. Nie realizuje prostego wyszukiwania po dacie czy gotowego diff dwóch dat (to funkcje *innego* oficjalnego konektora legalize-dev/mcp: law_at_date i diff_law).

**Wniosek:** Legalize to wartościowe uzupełnienie do historii i innych jurysdykcji, nie zastępuje polskiego, urzędowego ISAP. Legalize-dev wymienia w repo legalize-pl około 34 115 pozycji PL, podczas gdy ISAP deklaruje >96 tys. aktów; metryki i daty nie są wprost porównywalne. Oba zbiory mogą zawierać luki. W aktualnej produkcyjnej allowliście wrappera Legalize NIE jest aktywny.

## 4. Domyślne Repertorium — regresja czy rozszerzenie?

Zmiana w pl_search z wymagane source:str na source:str='repertorium' jest **rozszerzeniem akceptowanych wejść**. Wywołania uprzednio poprawne z podanym source zachowują routing i normalizację, więc sama zmiana wartości domyślnej NIE wykazuje regresji funkcjonalnej dla wcześniejszych żądań.

Ale zmienia się kontrakt MCP: upstream tests/tools.lock.json ma source w required, aktualny tools/list wrappera ma required=[] i default='repertorium'. To świadomy drift schematu wymagający aktualizacji deskryptorów, dokumentacji i testów, mimo że stare wywołania pozostają dopuszczalne. Ścisłe klienty z przypiętymi deskryptorami mogą wymagać zatwierdzenia zmian.

Z tej samej ścieżki pl_search(Repertorium) startuje oddzielny asyncio.create_task(_prefetch_repertorium_hits), który w tle pobiera do trzech pozycji z SAOS/KIO/UODO i może zapisać pełne teksty do PostgreSQL. To niezależne rozszerzenie o skutkach ubocznych, nie konsekwencja konieczna domyślnego źródła. Wymaga oddzielnej decyzji o utrzymaniu i testów jego wpływu na obciążenie, kompletność i cache.

Nie zaimplementowano zbiorczego wyszukiwania we wszystkich MCP. Zapis source nadal wybiera jedno źródło; jeśli chce się fan-out, należy odrębnie zaplanować i zatwierdzić nową funkcję.

## 5. Proponowane dalsze prace — bez upoważnienia do wykonania

1. **Po akceptacji:** utrwalić chown w obrazie przez świadomą aktualizację Dockerfile (COPY --chown) i test bez utraty funkcjonalności. Nie wykonywać teraz rebuildów.
2. **Po akceptacji:** ustalić, czy token ma być montowany do kontenera jako plik, czy należy go skonfigurować wyłącznie po stronie klienta Cloudflare MCP Portal. Samo skopiowanie do wrappera nie usunie strony Access HTML w połączeniu Lex. Jeśli narzędzia blokują transfer sekretu, nie obchodzić blokady.
3. **Po akceptacji:** dodać publiczny endpoint KIO tylko ze świadomie wybranym hostname, metodą uwierzytelniania i dokładną trasą tunelu. Nie osłabiać istniejącego Access.
4. **Po akceptacji:** przyjąć jako świadomy kontrakt opcjonalne source Repertorium, zaktualizować lock deskryptorów, instrukcje i testy; osobno rozstrzygnąć prefetch.
5. **Po akceptacji:** jeśli Legalize będzie potrzebny, rozstrzygnąć wariant matematicsolutions/legalize-mcp vs legalize-dev/mcp, dostęp GITHUB_TOKEN, zakres jurysdykcji, źródło i format historycznych wersji.

**Zasada:** każda faza wymaga zapisanego planu i wyraźnego zatwierdzenia użytkownika; samo wykrycie problemu nie jest zgodą na jego naprawę.

## 6. Referencje

- https://github.com/matematicsolutions/legalize-mcp
- https://github.com/matematicsolutions/mcp-isap
- https://github.com/legalize-dev/legalize
- https://github.com/legalize-dev/mcp
- https://github.com/elconcept/mcp-prawo-wrapper/blob/main/src/prawo_pl_mcp/server.py
- https://github.com/elconcept/mcp-prawo-wrapper/blob/main/docker-compose.nas.yml
