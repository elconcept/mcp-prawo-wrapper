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


## 6. Kontynuacja NAS — testy i poprawka tożsamości źródła (9.11.2026)

### Środowisko i izolacja

- Stan starej produkcji ponownie odczytano przez Docker Engine: Portainer stack **58**, kontener healthy, UID:GID **1029:100**, obraz `sha256:4e3b30efe98937e1ee5b89e91721f6bfdd1ea7cbd165941d91030350d8c766bb` (`mcp-prawo-wrapper:local`), bez sieci `cf_mcp_cite` i bez docelowego bind mount. Nie zmieniano go.
- Utworzono **wyłącznie** `/volume1/legal/opracowania/zrodla_prawne_mcp`, właściciel `abogada` (UID 1029), grupa `users` (GID 100), uprawnienia `2770` (FileStation pokazuje podstawowe `770`). Bez zmian katalogów nadrzędnych i bez rekurencyjnego `chown`.
- Tymczasowy kontener jako `1029:100`, z bind mount wyłącznie tego katalogu i bez sieci, z sukcesem utworzył, odczytał i usunął plik testowy. Kod wyjścia 0.
- Obrazy testowe budowano **na NAS** przez Docker Engine ze wskazanego commitu GitHub; nie pobierano projektu na MacBooka. Wersja po poprawce: `mcp-prawo-wrapper:pr5-29798cc-test` (image ID `sha256:ea0391f57714b5be8a14aa077011957b6e49f1dfc38be8ba482f736ffb54ab44`).

### LIVE LEGAL-CITE i SAOS

- Z odrębnego kontenera w `cf_mcp_cite`: `tools/list` potwierdziło `verify_article(citation, na_dzien?)` oraz `list_acts`.
- `verify_article(citation="art. 23 DU/2024/917")`: `is_error=false`, 1615 znaków odpowiedzi z treścią art. 23 i metadanymi ELI; kontener zakończył się kodem 0. **Nie udowadnia to jeszcze scenariusza zimnej konwersji PDF.**
- Test kodu nowego obrazu z prawdziwym `mcp-saos`: `saos:316066` → pełna treść 21 708 znaków → zapis Markdown przez bind mount jako UID 1029 → `pl_get_document` / `md_store.read` 5 stron ze zgodnym SHA-256 `9b3e0a8cae8e7b0b6ea3b7c9bef82d1456eaa2ed9315f4f0d51400810917eb43`. Kod wyjścia 0.

### Repertorium → MD: znaleziony prawdziwy błąd mapowania

- E2E na pierwszym obrazie `cda73ff` z żywym Repertorium dla `I C 270/15`: 9 trafień, 9 zapisów MD, statusy **5 full / 4 fragment_only**.
- Rekord `ms:151020250000503_I_C_000270_2015_Uz_2016-04-07_001` błędnie otrzymał status `full`: automatyczny fallback PMI uznał samo pokrycie sygnatury `I C 270/15` za wystarczające, mimo jawnej przestrzeni `ms:`.
- Kontrola zapisanego dokumentu wykazała **rzeczywistą niezgodność źródła**: trafienie `ms:` opisuje *wyrok* z 19.01.2016, a zwrócony tekst PMI jest *postanowieniem* z 29.10.2015. Zapis testowy był zatem błędnie skojarzony z innym dokumentem.
- Commit `893c8f0335eec4f632c4381f3368c3b091b6c94e`: jawne nieobsługiwane prefiksy źródła nie uruchamiają fallbacku po samej sygnaturze; jedynie brak prefiksu pozwala na próbę PMI.
- Commit `29798ccdda4ee192bd515e81c0ca310f287d44e4`: test regresyjny dla `ms:` i zachowania oryginalnego fragmentu.
- Błędny plik wygenerowany **w tym teście** zachowano jako `.md.invalidated` (bez kasowania); nie jest odczytywany przez standardowe `pl_get_document(md)`. Nie zmieniano cudzych dokumentów.
- Powtórzone E2E na obrazie `29798cc`: 9 trafień, **4 full / 5 fragment_only**; rekord `ms:` ma `fragment_only`, prawidłowo zapisany plik i obowiązkowe ostrzeżenie. Kod wyjścia 0.

### Testy offline na NAS, Python 3.12

- Obraz oparty o `python:3.12-slim` uruchamia Python **3.12.16**, importuje `FastMCP`, `hydrate` i `md_store` jako UID 1029 z rootfs tylko do odczytu; kod wyjścia 0.
- Z dokładnego archiwum GitHub commitu `29798cc` uruchomiono w izolowanym kontenerze NAS: `pytest -q tests -k "not smoke"` → **80 passed in 3.10s**.
- `ruff check src/prawo_pl_mcp/hydrate.py tests/test_repertorium_md.py` → **All checks passed**. Pierwsza próba Ruff zakończyła się błędem uruchomienia binarki na testowym `/tmp` (nie błędem kodu); poprawiono środowisko tymczasowego kontenera i powtórzono z kodem 0.
- GitHub Actions `ci.yml` poszerzono o Ruff, build `Dockerfile.nas` i test importu runtime Python 3.12: commit `e7f3e4dc47c4785179ad0140cfa7ba64aa5b0f50`. **Brak zaobserwowanych przebiegów Actions; nie oznaczać CI jako green bez run ID.**
- Po testach usunięto 9 tymczasowych kontenerów. Nie usunięto produkcji, jej danych, usług, baz ani wolumenów.

### Bramka produkcji — nadal STOP

Osiągnięto: build i runtime Python 3.12 na NAS, test zapisu jako UID 1029, test pełnej treści SAOS, rzeczywisty E2E Repertorium → Markdown, regresję błędnego mapowania `ms:`, oraz rzeczywisty test `verify_article` po sieci `cf_mcp_cite`.

Pozostało: weryfikacja zimnego LEGAL-CITE dla PDF-only i jego czasu, sprawdzenie tożsamości/kompletności rzeczywistych dokumentów **NSA i PMI** (same długie fragmenty nie mogą być mylone z pełnymi dokumentami), regresja `format=text` Repertorium w warunkach LIVE, kompletny przegląd PR oraz **przetestowany rollback stacka 58**. Stary stack i obraz są zachowane. Nie scalać, nie wdrażać produkcyjnie przed tymi bramkami.


### Przygotowanie rollbacku (bez przełączenia)

- Nadano staremu obrazowi produkcyjnemu dodatkowy lokalny tag `mcp-prawo-wrapper:pre-pr5-20261109`; odczyt Docker Engine potwierdził niezmienny digest `sha256:4e3b30efe98937e1ee5b89e91721f6bfdd1ea7cbd165941d91030350d8c766bb`, zgodny z aktualnym kontenerem stacka 58.
- Pobraną bezpośrednio z Portainera oryginalną konfigurację stack 58 zapisano **tylko na NAS** w `/volume2/docker/_rollback/mcp-prawo-wrapper_stack58_pre_pr5_20261109.yml` (1978 bajtów). Ponowny odczyt przez FileStation i porównanie z bieżącym Portainer `StackFileInspect`: identyczna zawartość. Uprawnienia: katalog `0700`, plik `0600`, właściciel UID 1029. Treści nie wypchnięto do publicznego GitHub.
- Odrębny kontener z tagu `pre-pr5-20261109` jako UID 1029 uruchomił poprawnie Python 3.12.16 i import starej aplikacji (exit 0), po czym został usunięty.
- Procedura udokumentowana w `deploy/ROLLBACK_STACK_58.md` (commit `26610c34d2224001508d9ae0623a0ee49e3db8ec`).
- **Nie wykonywano jeszcze pełnego operacyjnego rollbacku stacka 58**. Produkcja pozostaje uruchomiona na starym obrazie; przed przełączeniem nadal obowiązuje STOP.
