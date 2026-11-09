# Rollback — Portainer stack 58 / mcp-prawo-wrapper

**Status 2026-11-09:** przygotowano artefakty i sprawdzono stary obraz w odrębnym kontenerze; **nie wykonano jeszcze testu faktycznego przełączenia i powrotu stacka 58**. Nie jest to zgoda na aktualizację produkcji.

## Punkty odniesienia

- Portainer environment: `3`; stack: `58` (`mcp-prawo-wrapper`).
- Aktualny obraz produkcyjny: `sha256:4e3b30efe98937e1ee5b89e91721f6bfdd1ea7cbd165941d91030350d8c766bb`.
- Zachowany lokalny tag obrazu: `mcp-prawo-wrapper:pre-pr5-20261109` wskazujący **dokładnie** na powyższy digest. Nie wykonywać prune tego obrazu.
- Kopia **oryginalnego**, przedwdrożeniowego pliku stacka z Portainera (1 978 bajtów) na NAS: `/volume2/docker/_rollback/mcp-prawo-wrapper_stack58_pre_pr5_20261109.yml`, katalog `0700`, plik `0600`, właściciel UID 1029. Plik nie jest przechowywany w publicznym GitHub.
- Referencyjny tag nowej wersji testowej: `mcp-prawo-wrapper:pr5-29798cc-test`; NIE podmieniać `mcp-prawo-wrapper:local` przed zakończeniem wszystkich bramek.
- Starą infrastrukturę i dane (ISAP, PostgreSQL, SAOS, sekrety, stare sieci) pozostawić bez zmian.

## Gotowość przed przełączeniem (STOP jeśli niespełniona)

1. Zakończone CI Python 3.12/pytest/Ruff/build, poprawne rzeczywiste testy źródeł NSA i PMI, cold PDF LEGAL-CITE, kompatybilność `format=text`, review PR.
2. Sprawdzić, że snapshot pliku stacka z Portainera 58 nadal jest zgodny z kopią NAS, a tag `pre-pr5-20261109` istnieje i wskazuje na stary digest.
3. Przed aktualizacją zapisać w dzienniku stacka: jego aktywny plik, listę sieci/mountów, obraz i identyfikator kontenera; unikać publikowania sekretów.
4. Zapewnić dostęp do Portainera także wtedy, gdy Cloudflare MCP jest niedostępne.

## Przywrócenie w razie niepowodzenia (po przyszłej aktualizacji)

1. W Portainerze wyświetlić stack `58`. Zastosować **zapisany oryginalny** `docker-compose.yml` z kopii NAS, zachowując identyczną konfigurację poprzednich sieci, bind mountów, sekretów i parametrów kontenera.
2. W czasie rollbacku wskazać stary obraz przez zachowany tag `mcp-prawo-wrapper:pre-pr5-20261109` lub niezmienny digest `sha256:4e3b30...`. **Nie budować ze zmienionego kodu**. Przywrócić stare repo/checkout tylko wtedy, gdy procedura wymaga budowania (preferowane odtworzenie obrazu bez build).
3. Redeploy wyłącznie stacka `58`. Nie usuwać danych Markdown, PostgreSQL, katalogów źródłowych ani innych stacków. Pozostawić konfigurację Cloudflare Access.
4. Sprawdzić po powrocie: obraz/digest kontenera, `healthy`, komplet poprzednich sieci, dotychczasowe montaże, `tools/list`, dotychczasowe `pl_search` i natywne `pl_call`.
5. Zanotować wynik i pozostawić PR jako Draft, jeśli przywrócenie było konieczne.

## Zrealizowane próby przygotowawcze

- Zweryfikowano, że tag `pre-pr5-20261109` wskazuje na ten sam image ID co działający wrapper.
- Uruchomiono odrębny kontener na tym tagu jako UID 1029, bez sieci i z rootfs read-only: import `prawo_pl_mcp.server` na Python 3.12.16, exit code 0.
- Potwierdzono, że produkcja wciąż `running/healthy` i używa starego digestu.
- **Pełny test operacyjnego rollbacku Portainera pozostaje niewykonany**, ponieważ produkcji dotąd nie przełączano. Nie oznaczać tej bramki jako PASS.
