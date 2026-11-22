# issue-31 / etap 4: Lighthouse mobile dla Przeglądu i strony pomysłu

- **Agent / model:** Claude Code (claude-opus-5-5)
- **Branch / commits:** `feat/issue31-jakosc-ui`, commit „perf: …” (etap 4)
- **Date:** 2026-11-22 03:15

## Goal
Issue #31, zadanie 3: Lighthouse (mobile) ≥ 90 dla Przeglądu (`/`) i strony pomysłu (`/#/pomysl/<id>`): lazy-loading
obrazów, `width/height`, `poland.json` tylko gdy potrzebny, cache statyki (ETag), WebP ≤ 150 KB.

## What was done
- **CLS (główna przyczyna wyniku < 90):** pierwszy element widoku miał `margin-top`, który zapadał się przez pusty
  `<main>` (marginesy łączą się z rodzicem). `<main>` skakał z y=92 na y=60/76 px i zmieniał wysokość z 92 na 667 px przy
  wstawieniu szkieletu. Poprawka: szkielet jest od razu w `index.html` (`aria-busy="true"`), `#view` ma
  `display:flow-root` i `min-height` (v3.css). Przesunięcie `main#view` 0,908 → 0 (ślad `PerformanceObserver`
  `layout-shift`, Pixel 5).
- **`poland.json` (92 KB) poza startem:** loader rysuje granicę z obrysu wbudowanego w `index.html` (`#pl-shape`,
  7 KB, był już tam od #35); usunięto pobieranie pełnego pliku przy starcie (`pages.js`). Pełny plik ładuje tylko
  `drawPoland()`: na `#/mapa`, `#/wdrozenia` i dla minimapy Przeglądu dopiero, gdy wchodzi w widok
  (`IntersectionObserver`, miejsce zarezerwowane `min-height`). Cache w zmiennej `POLAND` bez zmian. Osobny skrypt
  generujący obrys nie był potrzebny, bo obrys już istnieje w HTML.
- **Kompresja:** `GZipMiddleware(minimum_size=1024)` w `main.py` (bez Caddy odpowiedzi szły nieskompresowane).
- **Cache statyki:** obrazy, `icons.svg`, `poland*.json` → `Cache-Control: public, max-age=604800`; `app.js`,
  `pages.js`, `*.css`, `index.html` zostają `no-cache` (ETag → 304).
- **Obrazy:** każdy `<img>` w szablonach ma `width`, `height`, `decoding="async"`, poniżej pierwszego ekranu
  `loading="lazy"`. Wszystkie `.webp` w `static/` już były ≤ 150 KB (największy `sectors/A_rolnictwo.webp`,
  121 KB), więc nic nie przekompresowano. Hero to tło CSS (nie `<img>`), więc `fetchpriority` nie ma zastosowania.

## Evidence
Pomiar: `npx lhci collect --config=e2e/lighthouserc.json` (3 przebiegi na URL, mediana, emulacja mobile, throttling
symulowany Lighthouse), serwer `e2e/scripts/serve.mjs` (SQLite + `radar demo` + uvicorn), Windows 11, 12 vCPU,
Chromium 1254 z Playwrighta (na Windows chrome-launcher daje `spawn UNKNOWN`, więc Chromium uruchomiono z
`--remote-debugging-port=9222`, a lhci z `--settings.port=9222`; w CI na Linuksie wystarcza `CHROME_PATH`).
„Przed” = `origin/main` (0024c3a) w osobnym worktree, ten sam seed.

| URL | wynik (3 przebiegi) | mediana perf | a11y | FCP | LCP | TBT | CLS | bajty |
|---|---|---|---|---|---|---|---|---|
| `/` przed | 78 / 79 / 80 | **79** | 97 | 2164 ms | 4980 ms | 42 ms | 0,003 | 935 KB |
| `/` po | 99 / 99 / 99 | **99** | 100 | 1429 ms | 2078 ms | 15 ms | 0,005 | 518 KB |
| `/#/pomysl/1` przed | 62 / 62 / 64 | **62** | 96 | 2179 ms | 3730 ms | 28 ms | 0,927 | 522 KB |
| `/#/pomysl/1` po | 99 / 99 / 99 | **99** | 100 | 1419 ms | 1687 ms | 25 ms | 0,019 | 131 KB |

Pośredni pomiar (gzip + `poland.json` poza startem, bez poprawki CLS): `/` 74, `/#/pomysl/1` 75 przy CLS 0,91–0,93.
To pokazało, że wąskim gardłem było przesunięcie układu, nie transfer.

Raporty (reprezentatywny przebieg): `docs/reports/lighthouse/przeglad-mobile.report.{html,json}`,
`docs/reports/lighthouse/pomysl-mobile.report.{html,json}`, `manifest.json`. `npx lhci assert`: wszystkie asercje
spełnione (`categories:performance` ≥ 0,9 i `categories:accessibility` ≥ 0,9, mediana).

Testy: `app/tests/test_static_assets.py` (7 testów: WebP ≤ 150 KB, `<img>` z width/height i decoding, ETag + 304,
max-age obrazów, gzip, brak `poland.json` przy starcie) oraz e2e `routes.spec.ts` „pełny poland.json: nie przy
starcie, dopiero na mapie”.

## Result vs acceptance
- Lighthouse mobile ≥ 90 dla `/` i `/#/pomysl/<id>`: **pass** (99 i 99, lokalnie).
- lazy-loading, width/height: **pass** (test pytest).
- `poland.json` tylko gdy potrzebny: **pass** (pytest + e2e).
- cache statyki (ETag): **pass** (pytest: 304 dla `If-None-Match`).
- WebP ≤ 150 KB: **pass** (pytest).

## Tested and did not work
- Same gzip + odroczenie `poland.json`: 74–75 punktów; CLS był odpowiedzialny za ~25 punktów.

## Next
- Wynik na runnerach GitHuba może się różnić (wolniejszy CPU). Job `lighthouse` w CI blokuje przy < 0,9; jeśli zacznie
  się wahać, zapisać pomiary tutaj i decyzję w `.house/DECISIONS.md`, nie obniżać progu po cichu.
- Ilustracje 1600×1600 px wyświetlane jako 56–480 px (przewodnicy, kreator, puste stany): mieszczą się w limicie
  150 KB, ale mniejsze warianty zmniejszyłyby transfer na stronach, które je pokazują.
