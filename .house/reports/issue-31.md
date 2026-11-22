# issue-31: Jakość UI (Playwright, a11y, wydajność), testy obciążeniowe, scenariusz demo i pitch

- **Agent / model:** Claude Code (claude-opus-5-5)
- **Branch / commits:** `feat/issue31-jakosc-ui` od `origin/main` 0024c3a: etap 1 `2cc68cd`, etap 2 `33ab6f4`, etap 3 `88d161a`,
  etap 4 `e4fd770`, etap 5 `cc07023`, etap 6 `1b43d20`, etap 7 (CI, README, raporty): ostatni commit gałęzi
- **Date:** 2026-11-22 04:30

## Goal
Issue [#31](https://github.com/Eterphis/hacknation-2026-innovation-radar/issues/31): Playwright i axe w CI, Lighthouse
mobile ≥ 90, locust 50 rps na profilu 2 vCPU / 4 GB z cache, tryb ciemny v3, scenariusz demo (5 min) i pitch PDF.
Zasada nadrzędna: stabilne rozszerzenie, nic, co działa, nie zostaje zepsute; każda zmiana w aplikacji ma test.

## What was done
**Etap 1: e2e** (`e2e/`, Node tylko jako narzędzie testowe): Playwright 1.65.0, @axe-core/playwright 4.14.0,
@lhci/cli 0.16.0 (dokładne wersje, `package-lock.json`). 4 projekty (desktop/mobile × jasny/ciemny), `reducedMotion:
'reduce'`, `retries` 0 lokalnie / 1 w CI, reporter ostrzegający o niestabilnych testach, `forbidOnly` w CI.
`fixtures.ts`: strażnik konsoli (error, pageerror, odpowiedzi ≥ 400 z własnego originu; lista wyjątków pusta),
unikalny voter na test, ID pomysłów i persony z API. `routes.ts`: jedna lista tras; test sprawdza, że każdy klucz
`ROUTES` aplikacji ma wpis. Serwer lokalny `scripts/serve.mjs` (SQLite + `radar demo` + uvicorn; `radar demo` na
SQLite działa bez zmian). Specy: `routes`, `wizard`, `save-like`, `layout`, `a11y`, `keyboard`, `demo`.
Zmiany w aplikacji wykryte lub wymuszone przez testy:
- router ustawia `aria-busy` na `<main>` (testy czekają na to zamiast na sleep);
- **błąd:** kreator otwarty z gołego `#/dopasuj` po ostatnim pytaniu nie pokazywał wyników (ten sam hash, brak
  `hashchange`) → poprawione, test `wizard.spec.ts`;
- przycisk „Pokaż wyniki” po roli i 2 odpowiedziach (bez niego żadna ścieżka nie dawała „3 kliknięć”; Q-009);
- fokus przechodzi na nowe pytanie kreatora;
- Rolki nie miały nagłówka: `h1` (sr-only) i tytuły jako `h2`;
- **błąd:** na 375 px oznaczenie „ilustracja AI” w Rolkach było ukryte (`display:none`) → widoczne; grafiki AI mają
  `data-ai`, kreator i puste stany mają widoczny podpis „ilustracja AI”, portret przewodnika plakietkę „AI”.

**Etap 2: dostępność.** axe (wcag2a/aa, 21a/aa) na 22 widokach i w stanach po interakcji (każdy krok kreatora,
każda zakładka pomysłu, wyszukiwarka, otwarty klaster, panel przewodnika) w obu motywach. Naprawione:
`color-contrast` (biały na `#F0627A`, 3,11:1, w ciemnym „Porównaj”) przez token `--btn` (5,2:1);
`aria-tooltip-name` (pusty `role="tooltip"` → `aria-hidden`); `label-content-name-mismatch` (94 węzły na projekt:
przyciski polubień, portret przewodnika); `nested-interactive` (mapa `role="img"` z fokusowalnymi województwami →
`role="group"`). Zakładki strony pomysłu i „Na dziś” jako wzorzec ARIA tabs (strzałki, Home/End, roving tabindex,
`aria-controls`, `tabpanel`). **Błąd:** zwinięte klastry miały niewidoczne pomysły w kolejności Tab → `visibility:
hidden`. Escape w wyszukiwarce i panelu przewodnika zwraca fokus do elementu, który je otworzył.

**Etap 3: tryb ciemny v3.** Tokeny `--img-tint`, `--scrim-end`, `--scrim-solid` w `:root` i `[data-theme=dark]`:
przygaszone jasne ilustracje (hero, banery, strona pomysłu, kafle, klastry, rolki), scrim na całej szerokości
banera, przełączniki na banerze na pełnym tle. Zrzuty przed/po: `docs/screenshots/v3-{przeglad,klastry,pomysl,
dla-samorzady}-ciemny-{przed,po}.png`, `v3-rolki-375-ciemny-{przed,po}.png`.

**Etap 4: wydajność** (szczegóły: `.house/reports/lighthouse.md`): CLS 0,93 → 0,02 (zapadanie marginesów przez
pusty `<main>`; szkielet w `index.html`, `display:flow-root`), `poland.json` poza startem (loader rysuje granicę z
obrysu w HTML; pełny plik tylko na mapie i dla minimapy w widoku), `GZipMiddleware`, `max-age=604800` dla obrazów,
`icons.svg` i `poland*.json`, `width/height/decoding` na każdym `<img>`. WebP: wszystkie były już ≤ 150 KB.

**Etap 5: obciążenie i cache** (szczegóły: `.house/reports/load.md`): `radar/api/cache.py` (wersja danych + TTL,
`reset_api_cache()` w conftest), korpus `/api/match`, odpowiedź `/api/ideas` (+ koniec N+1), `/api/clusters` (wcześniej
TTL bez unieważniania). `loadtest/` z locustem, limitami compose i profilem SQL.

**Etap 6: demo i pitch:** `docs/scenariusz-demo.md`, `e2e/tests/demo.spec.ts`, `docs/pitch/slides.html`,
`e2e/scripts/pitch.ts` → `docs/pitch/pitch.pdf` (10 slajdów, każda liczba z przypisem źródła i godziną),
`docs/pitch/narracja.md`.

**Etap 7: CI:** joby `e2e`, `lighthouse`, `load-smoke` dopisane na końcu `ci.yml`; 6 istniejących jobów bez zmian
(`git diff` pokazuje tylko dopisane linie). README: sekcja „Testy UI i jakości”.

## Evidence
| Co | Komenda | Wynik |
|---|---|---|
| pytest app, baza | `cd app && python -m pytest -q` (start) | 125 passed, 1 skipped (na `1b6ea1f`); po merge'u #37 do `main`: 129 passed |
| pytest app, koniec | jw. | **140 passed, 1 skipped** (+7 `test_static_assets.py`, +4 `test_api_cache.py`) |
| pytest harvester | `python -m pytest -q tests` | 233 passed (start i koniec) |
| e2e lokalnie (SQLite) | `cd e2e && npx playwright test` | 218 passed |
| e2e na compose (Postgres, demo) | `E2E_BASE_URL=http://localhost:8000 npx playwright test` | 218 passed (4,1 min) |
| e2e stabilność | `npx playwright test --repeat-each=3` | 1. próba: 652 passed, **2 failed** (`mobile-light` routes klastry/odkrywaj: `ERR_INSUFFICIENT_RESOURCES` i timeout `page.screenshot`; równolegle szedł pytest, host przeciążony). Przyczyna w teście: zrzuty całej strony w DPR 2,75. Poprawka: `scale: "css"`. 2. próba: **654 passed** (10,8 min), 0 flaky |
| axe | `a11y.spec.ts`, 4 projekty | 0 naruszeń dowolnej wagi (critical, serious, moderate) po poprawkach; przed: 0 critical, 6 węzłów `color-contrast` w ciemnym, 94 `label-content-name-mismatch`, 31 `aria-tooltip-name`, 4 `nested-interactive` na projekt |
| Lighthouse mobile | `npx lhci collect/assert` | `/` 79 → **99**, `/#/pomysl/1` 62 → **99**, a11y 100 |
| locust 3 min | `.house/reports/load.md` | 19,9 → **56,7 rps**, 0 błędów, p95 74 ms |
| demo | `demo.spec.ts --repeat-each=3` | 6 passed |
| pitch | `E2E_BASE_URL=http://localhost:8000 node scripts/pitch.ts` | 10 slajdów, `docs/pitch/pitch.pdf` |

Checklista `.house/protocols/demo-checklist.md` (to, co da się sprawdzić lokalnie):
- [ ] URL wdrożenia w incognito na innym urządzeniu: nie sprawdzone (brak wdrożenia w tym zadaniu).
- [x] Złota ścieżka od czystej sesji: `demo.spec.ts` (świeży kontekst przeglądarki).
- [x] Dane demo bez lokalnego stanu: `radar demo`, seed deterministyczny.
- [ ] Klucze API w produkcji: nie dotyczy trybu demo, nie sprawdzone.
- [x] Stany ładowania się kończą: `aria-busy` znika, szkielety znikają na każdej trasie (routes.spec).
- [x] Bez klucza: tryb demo oznaczony („przykład”, stopka „Tryb demo”).
- [x] Konsola bez błędów: strażnik w każdym teście e2e.
- [x] Rozdzielczość rzutnika i telefonu: projekty 1280×800 i 375×812.
- [ ] Playwright na wdrożonym URL: możliwy (`E2E_BASE_URL=<url> npx playwright test`), nie uruchomiony.
- [x] Zapasowe zrzuty: artefakt CI `e2e-screens`; [ ] nagranie zapasowe: nie zrobione.
- [x] README zgodne z tym, co zbudowane (sekcja „Testy UI i jakości”).
- [ ] Licencje / `house export`, wideo, zgłoszenie z innej maszyny: poza zakresem.

## Result vs acceptance
- CI z Playwright i axe zielone: **lokalnie pass** (218/218 na SQLite i na compose); w GitHub Actions: zobacz PR
  (wynik jobów zapisany tam, nie tutaj).
- axe: 0 critical i 0 `color-contrast` na wszystkich trasach w obu motywach: **pass**.
- Lighthouse mobile ≥ 90 dla `/` i `/#/pomysl/<id>`: **pass** (99, 99), raporty w repo.
- Load test w repo, 50 rps przed i po, wąskie gardła: **pass** (`.house/reports/load.md`).
- Scenariusz demo i pitch w `docs/`: **pass**; `demo.spec.ts` zielony.
- Brak poziomego przewijania na 375 px, `prefers-reduced-motion`, tylko Lucide, grafiki AI oznaczone: **pass** (testy).
- „3 kliknięcia do wyniku” < 20 s: **pass** w interpretacji z Q-009 (~3 s lokalnie).
- Scenariusz „klastry AI w zdrowiu”: **fail wobec danych** (nie ma takiego klastra w demo; Q-008).

## Tested and did not work
- Pierwsze `--repeat-each=3`: 2 porażki z wyczerpania zasobów Chromium przy zrzutach całej strony w natywnej gęstości
  Pixel 5; naprawione przez zrzuty w skali CSS, nie przez ponawianie.
- Lighthouse na Windows: chrome-launcher z Chromium Playwrighta kończy się `spawn UNKNOWN`; obejście: Chromium z
  `--remote-debugging-port` i `lhci --settings.port`. W CI (Linux) `CHROME_PATH` wystarcza.
- Gzip i odroczenie `poland.json` bez poprawki CLS dawały tylko 74–75 punktów Lighthouse.
- Bez cache API: ~20 rps (nasycony 1 proces z limitem 1,2 CPU).

## Next
- Q-008: dopisać syntetyczne próbki „AI w zdrowiu” i pomysł z Pomorza gotowy do wdrożenia.
- Q-009: potwierdzić „Pokaż wyniki” jako interpretację „3 kliknięć”.
- Wyniki jobów `e2e`, `lighthouse`, `load-smoke` na runnerach GitHuba: przy wahaniu Lighthouse wokół 0,9 zapisać
  pomiary w `.house/reports/lighthouse.md`, decyzję (np. job nieblokujący) w `.house/DECISIONS.md`.
- `GET /api/clusters` przed tą zmianą nie miał resetu cache między testami; teraz ma (reset w conftest).
