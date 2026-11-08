# PLAN: uprawnienia i poświadczenia MCP-PRAWO — 2026-11-08

**Status: DO ZATWIERDZENIA. NIE WYKONYWAĆ ZMIAN PRZED WYRAŹNĄ AKCEPTACJĄ.**

Powiązanie: [audyt architektury](../docs/AUDYT_mcp_prawo_upstream_i_regresje_20261108.md) i [zasada zatwierdzania zmian](./20261108_plan_zatwierdzenia_architektury_mcp_prawo.md).

## 1. Zakres polecenia

- Przenieść/udostępnić poświadczenia Cloudflare Access aktualnie używane przez Explorer do planowanego zastosowania w MCP-PRAWO.
- Ujednolicić właściciela **plików aplikacji i jej sekretów** na UID 1029, GID 100.
- Zweryfikować, że kontener `mcp-prawo-wrapper` uruchamia proces aplikacji jako `1029:100`.
- Zachować Cloudflare Access, oryginalne konektory MCP, Repertorium/Tor, bazę, portal i wszystkie istniejące dane bez niezamówionych zmian.

**Uwaga dotycząca nazw:** aktywny kontener z kodem agregatora nosi nazwę `mcp-prawo-wrapper`; `mcp-prawo` jest identyfikatorem jego serwera w Cloudflare MCP Portal.

## 2. Stan potwierdzony wyłącznie przez odczyt

- Explorer: `/app/.env` **nie istnieje**; poświadczenia są w `/app/.cf-service-token` (host: `/volume2/docker/lex_mcp_explorer/.cf-service-token`), właściciel `1029:100`, tryb `0600`. Nie odczytywano wartości sekretów.
- Explorer działa z UID 1029 i GID 100. Poświadczenia nie są wystawione jako `CF_ACCESS_CLIENT_ID` i `CF_ACCESS_CLIENT_SECRET` w środowisku procesu — aplikacja odczytuje plik sekretu.
- Kontener `mcp-prawo-wrapper`: proces UID 1029, GID 100. Sekret DB `/run/secrets/db_password` ma wymagany właściciel (sprawdzono metadane).
- Pliki kodu w obrazie w `/app/src`, `pyproject.toml` i inne pliki aplikacji są obecnie `root:root` i czytelne dla procesu, ale nie należą do `1029:100`. Na hoście katalog `/volume2/docker/mcp-prawo-wrapper` ma mieszane ownership `root:root` / `abogada:users`.
- W konfiguracji Dockerfile występuje `USER 1029:100`, ale kopia `COPY src /app/src` nie przypisuje własności plików do 1029:100.
- Cloudflare MCP Server `mcp-prawo` wskazuje na `https://orzeczenia.xlap.pl/mcp` i ma status `error` z powodu otrzymania strony HTML Cloudflare Access, zamiast odpowiedzi MCP. To osobny problem warstwy **klient Cloudflare → chroniony endpoint**.

## 3. Ważne rozróżnienie: skopiowanie tokena a uwierzytelnienie przez Cloudflare

Poświadczenia `CF-Access-Client-Id` / `CF-Access-Client-Secret` są poświadczeniami **klienta** wobec Cloudflare Access. Skopiowanie ich do kontenera wrappera nie spowoduje automatycznie, że Cloudflare MCP Portal zacznie przekazywać je w żądaniach do tego kontenera. Dlatego:

1. Kopia sekretu w wrapperze, o którą prosi użytkownik, może zostać wykonana jako odrębny, jednoznaczny krok, ale **nie jest dowodem naprawy połączenia Lex**.
2. Żeby Lex odzyskał narzędzia, po zaakceptowaniu osobnego etapu trzeba skonfigurować poświadczenia **upstream** w rejestracji `mcp-prawo` w Cloudflare MCP Portals (typ `bearer`, niestandardowe nagłówki Access) i wykonać test `initialize`, `tools/list` oraz `pl_call`.
3. Poświadczenia nie trafią do GitHub, pliku compose, Dockerfile, logów, odpowiedzi narzędzi ani żadnych publicznych artefaktów.

Wcześniejsze próby automatycznego przekazywania sekretów przez narzędzia były blokowane. Jeśli blokada pozostanie, **nie obchodzić jej**; zatrzymać etap i zgłosić ograniczenie.

## 4. Proponowana sekwencja działań (wyłącznie po zatwierdzeniu)

### A. Przygotowanie i zabezpieczenie danych
- Potwierdzić istnienie źródłowego pliku i jego uprawnienia bez wyświetlania zawartości.
- Utworzyć docelowy katalog `/volume2/docker/mcp-prawo-wrapper/.secrets/` z `0700`, `1029:100`. Upewnić się, że ścieżka jest wyłączona z Git (`.git/info/exclude` lub zatwierdzona reguła ignorowania).
- Wykonać atomową kopię sekretu z Explorera do `.secrets/cf-access-token`, właściciel `1029:100`, `0600`; bez rozszerzania uprawnień do `0777`. Zweryfikować tylko rozmiar/hash i metadane (hashy nie publikować).
- Upewnić się, czy konieczne jest faktyczne montowanie kopii do aplikacji; nie wprowadzać niewykorzystywanej zmiennej ani nie zwiększać ekspozycji sekretu bez uzasadnienia.

### B. Własność plików aplikacji
- Uzgodnić definicję „wszystkie pliki”: **pliki aplikacji w obrazie `/app` i katalog projektu na NAS**, bez systemowych katalogów obrazu `/usr`, `/etc`, `/lib` i obcych wolumenów.
- Zachować snapshot/backup metadanych (path, uid, gid, mode) przed zmianą.
- Na hoście: zmienić właściciela katalogu `/volume2/docker/mcp-prawo-wrapper` i jego zawartości na `1029:100` (w tym `.git`) z uwzględnieniem symlinków i atrybutów ACL; potwierdzić wpływ na operacje Git i Portainer.
- W obrazie, po zaakceptowaniu zmiany Dockerfile, ustawić `COPY --chown=1029:100` lub równoważny bezpieczny mechanizm dla `/app`; nie zmieniać semantyki aplikacji.
- Uprawnienia plików zachować zgodne z użyciem, bez nadawania `0777`; sekret `0600`, katalog sekretów `0700`, pliki kodu odczytywalne dla UID 1029.

### C. Kontrolowane wdrożenie i testy
- Przeprowadzić build na zatwierdzonym repo/commicie, bez aktualizacji zależności upstream i bez refaktoryzacji.
- Restart tylko `mcp-prawo-wrapper`, w dopuszczonym oknie; nie restartować Repertorium, Tor ani innych konektorów.
- Potwierdzić UID/GID procesu, `stat` wszystkich plików aplikacji (bez niedozwolonych właścicieli), uprawnienia sekretów i brak obecności sekretów w logach/środowisku/obrazie.
- Test MCP przez LAN: `initialize`, `tools/list` (5 narzędzi), `pl_list_sources` i nieinwazyjny `pl_call`. Osobny test przez Lex tylko jeśli etap konfiguracji Cloudflare również będzie zaakceptowany.
- Jeśli weryfikacja nie powiedzie się, wstrzymać dalsze zmiany i przedstawić raport; nie wykonywać samowolnego rollbacku.

## 5. Czego plan NIE autoryzuje

Żadnego usuwania źródeł z Lex, zmiany hasła/tokenu, chmod 777, obniżenia poziomu ochrony Cloudflare Access, kasowania cache/PostgreSQL, zmian Tor/Repertorium, semantyki `pl_search` / `pl_get_document`, zmian upstream, ukrytego uruchamiania usług, ani automatycznego rollbacku.

## 6. Warunki akceptacji

- Użytkownik akceptuje konkretny zakres sekcji 4 (A+B+C) i sposób postępowania z kopią sekretu.
- Użytkownik osobno akceptuje konfigurację uwierzytelnienia upstream w Cloudflare, jeśli oczekiwane jest naprawienie komunikacji w Lex.
- Po wdrożeniu udokumentowane są wyniki `stat`, UID/GID, testy MCP i status Lex, bez publikowania sekretów.
- W razie ujawnienia nieplanowanej zmiany lub ryzyka: zatrzymanie i ponowna akceptacja.

**Stan obecny:** tylko dokument planu. Bez kopiowania poświadczeń, chown, chmod, przebudowy/restartu kontenerów i zmian Cloudflare.
