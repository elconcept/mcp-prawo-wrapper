# RAPORT REALIZACJI — mcp-prawo-wrapper, faza D (2026-11-09)

Dokument powiązany:
`_PLAN/20261109_plan_wykonawczy_mcp_prawo_pmi_eureka_eu_compliance.md`
na gałęzi `audit/upstream-preservation-20261108`.
To jest **dziennik wdrożenia roboczego**, nie stwierdzenie przełączenia produkcji.

## 1. Stan źródeł potwierdzony LIVE

Portainer, środowisko 3, 2026-11-09:

| Źródło | Stos/kontener | Status / co rzeczywiście sprawdzono |
|---|---|---|
| Repertorium | 19 / mcp-repertorium | healthy; tools/list i wywołanie szukaj_repertorium(format=json) zwraca zachowany JSON z `trafienia` |
| EUREKA | 64 / mcp-eureka | healthy; tools/list: search, get_interpretation, search_by_signature, list_categories; list_categories działa |
| EU-COMPLIANCE | 65 / mcp-eu-compliance | healthy; tools/list: eu_search, eu_article, eu_compare, eu_check_applicability, eu_evidence; eu_article(GDPR, 33) działa |
| PMI | 60 / pmi | healthy; tools/list: pmi_search, pmi_get_document, pmi_get_article, pmi_list_acts; wyszukiwanie KPK działa |
| LEGAL-CITE | 49 / legal-cite | healthy; **wewnętrzny port 8080**, sieć `cf_mcp_cite`; aktualny wrapper nie jest jeszcze w tej sieci |
| Wrapper | 58 / mcp-prawo-wrapper | healthy, **stary obraz i konfiguracja produkcyjna**, zmian nie wdrożono |

Kontrolę dostępności i wywołania MCP wykonano z wnętrza dotychczasowego kontenera wrappera bez zmiany jego plików i konfiguracji. EUREKA, EU-COMPLIANCE, PMI i Repertorium są osiągalne przez istniejące sieci. LEGAL-CITE wymaga zaplanowanego podpięcia do `cf_mcp_cite`.

## 2. Zmiany kodu w PR #5

Gałąź: `feat/repertorium-md-fulltext-20261109`.
PR: https://github.com/elconcept/mcp-prawo-wrapper/pull/5 (Draft).

- `pl_search`: domyślnie Repertorium `format=json`, zachowane oryginalne `trafienia`; próba odczytu źródła, bez gubienia trafień po niepowodzeniu.
- `hydrate.py`: zachowanie snippetów, rozpoznawanie wybranych ID źródeł, jawny `fragment_only` z obowiązkiem poinformowania użytkownika; `article_only` dla artykułów.
- `md_store.py`: osobne pliki z deterministycznymi nazwami, YAML frontmatter, checksum, paginacja, weryfikacja `expected_sha256`, odmowa ścieżek ucieczkowych i dowiązań, atomowy zapis w wydzielonym katalogu.
- `registry.py`: LEGAL-CITE zamiast ISAP; PMI zamiast LEGALIZE; EUREKA i EU-COMPLIANCE.
- `docker-compose.nas.yml`: wyłącznie bind `/volume1/legal/opracowania/zrodla_prawne_mcp:/legal_sources:rw`, sieć `cf_mcp_cite`, adres LEGAL-CITE `http://legal-cite:8080/mcp`; bez podłączania danych SAOS i PostgreSQL.
- `pool.py`: osobny timeout na zimne odczyty LEGAL-CITE (240 s w compose); `README.md`, instrukcje MCP, testy i blokada deskryptorów uaktualnione.
- Usunięto tylko **kod** starego lokalnego cache PostgreSQL/SAOS z gałęzi; żadne dane i usługi NAS nie były usuwane.

## 3. Kontrole wykonane

- `pytest -q tests -k 'not smoke'`: **79 passed** (Mac, Python 3.14, środowisko izolowane).
- `ruff check` na zmienionych modułach: PASS.
- `git diff --check`: PASS.
- Parser `docker-compose.nas.yml`: PASS; wszystkie aliasy sieci mają deklaracje.
- GitHub: commit i push gałęzi, PR #5 pozostaje Draft.
- LIVE wywołania odrębnych MCP potwierdzają działanie wybranych narzędzi. Osobno w izolowanej kopii nowego kodu na Mac wykonano pełne Repertorium JSON → SAOS 316066 (21 708 znaków) → Markdown → odczyt 5 stron i SHA-256. To NIE jest test docelowego bind mount Synology.

## 4. Przed produkcyjnym przełączeniem

1. Zweryfikować zgodność nowej wersji pod Python 3.12 w CI i zakończyć review PR.
2. Utworzyć wyłącznie dedykowany katalog Markdown w `/volume1/legal`, sprawdzić uprawnienia dla UID 1029 (nie robić rekurencyjnego chown i nie montować całego legal).
3. Przetestować nowy obraz w osobnym środowisku/kontenerze z prawdziwym bind mountem: wyszukiwanie Repertorium → pełna treść źródła → zapis MD → `pl_get_document(md)` z SHA między stronami; testy błędów źródła, symlinków i uprawnień.
4. Zweryfikować LIVE `tools/list` i `verify_article` z LEGAL-CITE przez sieć `cf_mcp_cite` z limitem uwzględniającym cold PDF oraz kilka dokumentów SAOS/NSA/PMI; zadbać o poprawne oznaczanie kompletności i zgodność ID.
5. Dopiero po bramkach aktualizować stack 58 z możliwością rollbacku. Po aktualizacji sprawdzić health, wszystkie 5 tooli wrappera i odpowiedź `pl_search` z zapisem MD.
6. Nie usuwać legacy ISAP, PostgreSQL, starych danych ani innej infrastruktury bez odrębnego polecenia. Zachować Cloudflare Access.

## 5. Znane ograniczenia roboczego kodu

- Paginacja SAOS offset/limit jest obecnie składana z walidacją identyfikatora, zakresów i długości całkowitej; wielostronicowe odpowiedzi innych źródeł nadal mogą być oznaczone jako `fragment_only`.
- Nierozstrzygnięte mapowanie `sn:` jest kierowane po dokładnej sygnaturze do PMI; niedostępne/niepasujące dokumenty muszą pozostać `fragment_only`.
- SAOS sprawdzono na rzeczywistym rekordzie 316066; oznaczenie `full` w pozostałych źródłach wymaga prób na faktycznych rekordach.
- Nie zweryfikowano jeszcze fizycznych zapisów plików w `legal` ani produkcyjnego `verify_article` po nowej ścieżce sieciowej.
- Nie zaimplementowano automatycznego commit/push/pull dla materiałów Markdown do innych klonów (nie jest częścią tej fazy).
