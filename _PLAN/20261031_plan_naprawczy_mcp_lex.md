# mcp-prawo-wrapper i portal lex — plan naprawy integracji odpowiedzi MCP

> Audyt 2026-10-31: testy narzędzi przez portal `lex`, wywołania bezpośrednie w kontenerach, inspekcja kodu elconcept. **Plan**, nie wdrożenie. **POTWIERDZONE** = fakt testowy lub z kodu; **DO SPRAWDZENIA** = hipoteza.

## Reguły wdrożeniowe
- Polskie zapytania, polska treść, polskie tytuły i polskie błędy. Brak selektora języka w publicznym MCP. Identyfikatory (CELEX/ELI/ECLI, sygnatury, techniczne nazwy) pozostają zgodne ze źródłem.
- `content` i `structuredContent` muszą być zachowane przez kontener, Cloudflare, portal `lex` i klienta. Tekst urzędowy należy oddzielić od komentarza, a stan prawny oznaczyć datą/źródłem.
- Przed produkcyjnym wdrożeniem: test fixture i regresja → staging → smoke end-to-end → kopia stanu → bezpieczny rollout i rollback. Nie ujawniać danych identyfikujących, tokenów ani pełnych logów dostępu.

## Materiał dowodowy i zasięg
- **POTWIERDZONE:** klient wywołujący przez portal `lex` widzi dla EU-COMPLIANCE, KRS i części SAOS/NSA przede wszystkim `structuredContent.citations`/metadane, podczas gdy MCP w kontenerze (i Cloudflare `eu-compliance.xlap.pl/mcp`) zwrócił pełne pole `content`. Wniosek diagnostyczny: w łańcuchu portal–adapter–klient znika możliwość konsumpcji merytorycznego tekstu, nie należy jeszcze przypisywać winy konkretnemu komponentowi bez logu surowego MCP po obu stronach.
- **POTWIERDZONE:** `mcp-prawo-wrapper` w README deklaruje ujednolicenie argumentów 10 konektorów, z `pl_search`, `pl_get_document`, `pl_call`, `pl_coverage`, `pl_list_sources`, normalizacją stron i paginacją dokumentów.
- **POTWIERDZONE:** `deploy/grounding-prawo/compose.yaml` ustawia `PRAWO_PL_MCP_SOURCES=saos,nsa,ustawy`, odsyła do ich endpointów HTTP na NAS, a nie do wszystkich serwerów w portalu. W spisie aktualnie działających kontenerów Portainera nie potwierdzono osobnego `mcp-prawo`; projekt należy traktować jako **potencjalną warstwę integracyjną**, nie jako dowiedziony etap obecnej ścieżki `lex`.
- **DO SPRAWDZENIA:** czy portal Cloudflare MCP Portals, jego tool-proxy/codemode lub klient ChatGPT odrzuca tekst `content` przy obecności `structuredContent`, czy jest to tylko reprezentacja obiektu zwrotnego w bieżącej sesji.

## Plan
1. **P0 — instrumentacja punktów pośrednich:** dla nieosobowych, krótkich fixture odpowiedzi (`eu_article GDPR 33`, `krs_get_board 0000028860`, `saos_get_judgment 166511`) porównać pełne MCP JSON-RPC `tools/call` na: stdio kontenera, bezpośredni HTTP, publiczny Cloudflare Tunnel, upstream Portals, tool-call z portalu, klient końcowy. Logować tylko `content_present`, `content_length`, `citations_count`, SHA-256 pola tekstowego, request ID i status, bez pełnego payloadu.
2. **P0 — kontrakt transportowy:** wynik musi zawierać jednocześnie `content: [{type:'text',text:'…'}]` i `structuredContent: {citations:[…],…}` bez skracania `content` do `snippet`. Obsłużyć różnice SSE/JSON, sesji MCP, serializacji JSON-RPC i wieloblokowych odpowiedzi; nie mutować treści prawniczej w proxy.
3. **P1 — polski interfejs:** dla wszystkich narzędzi widocznych w `lex` polskie opisy i odpowiedzi, bez `lang` w UI/schema; mapowanie języka domyślnie PL. Znormalizować nazwy parametrów bez psucia starych klientów (wersja kontraktu). Ustawienia języka nie mogą być użytkownikowi potrzebne.
4. **P1 — narzędzia jednolite:** `pl_search` i `pl_get_document` wymuszają źródło, stan prawa, długość treści, offset/stronę, `hasMore`; `pl_call` zwraca pełny wynik natywnego narzędzia i dodatkowe citations, bez scalania rozbieżnych struktur w jeden ubogi rekord.
5. **P1 — portal Cloudflare:** sprawdzić konfigurację `lex.xlap.pl/mcp`, mapy upstream i policies; nie tworzyć osobnej polityki na każdy MCP. Rozróżniać błąd uwierzytelnienia `authorization failed` od awarii transportu/upstream i od obcięcia odpowiedzi. Weryfikować te same testy bezpośrednio poza portalem.
6. **P2 — regressions i release:** złote fixtures na 9 kontenerów; test ten sam tool 3 ścieżkami, SHA tekstu i check URL PL; raport `ok/partial/error` z przyczyną. Zmiany dopiero po PR, testach i kontrolowanym wdrożeniu; nie przełączać od razu istniejących upstreamów.

## Akceptacja
- `lex` zwraca pełne `content` i `structuredContent` dla artykułu, decyzji i orzeczenia. Kontrola checksum wykazuje brak ubytku w łańcuchu.
- Wszystkie publiczne narzędzia/komunikaty wyłącznie PL, bez selektora języka; sygnatury i CELEX pozostają oryginalne.
- Test negatywny odróżnia `brak wyników` od `upstream_error` i `authorization failed`, bez wycieku sekretów.

## Pliki / dowody
`src/prawo_pl_mcp/server.py`, `pool.py`, `pagination.py`, `registry.py`, `deploy/grounding-prawo/compose.yaml`, Cloudflare MCP Portals `lex` oraz dziewięć upstreamów.
