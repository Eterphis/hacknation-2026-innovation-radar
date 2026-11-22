---
title: "[Runda 3 · E] Jakość UI (Playwright, a11y, wydajność), testy obciążeniowe, scenariusz demo i pitch"
labels: [ui, qa, pitch, handoff]
---
**Dla:** piątej osoby (QA + front + pitch). Wklej agentowi całość.

## Najpierw przeczytaj
- `docs/stack.md` (technologie i modele) i `docs/sciezki-uzytkownikow.md` (6 ścieżek, zasady UI: jedna obietnica na wejściu, szczegóły na żądanie, bez rozciągniętych pól, polskie barwy).
- Front: `app/radar/api/static/{index.html, app.js, pages.js, app.css, v3.css}`. `pages.js` ma nowe strony: `#/pomysl/<id>`, `#/klastry`, `#/dopasuj` (kreator z rozgałęzieniami), `#/rolki`, `#/portfel?tab=zapisane`.
- Zrzuty obecnego stanu: `docs/screenshots/v3-*.png`.

## Zadania
1. **Playwright w CI (zaległe z #24).** Testy e2e na compose w trybie demo: każda trasa ładuje się bez błędów konsoli; ścieżka „3 kliknięcia do wyniku” (rola → 2 odpowiedzi → wyniki) < 20 s; zapisz pomysł → widać go w Portfel → Zapisane; polub → licznik rośnie; kreator wielokrotnego wyboru nie przeładowuje widoku. Zrzuty desktop i 375 px, jasny i ciemny, jako artefakty CI.
2. **Dostępność.** axe-core na wszystkich trasach: zero błędów krytycznych; nawigacja klawiaturą po kreatorze, zakładkach strony pomysłu i klastrach; kontrast AA także w trybie ciemnym (sprawdź nowe banery i rolki).
3. **Wydajność.** Lighthouse (mobile) ≥ 90 dla Przeglądu i strony pomysłu: lazy-loading obrazów, `width/height`, preload `poland.json` tylko gdy potrzebny, cache statyki (ETag), obrazy WebP ≤ 150 KB.
4. **Testy obciążeniowe (zaległe z #23).** locust: 50 rps na `/api/match`, `/api/ideas`, `/api/clusters`, `/api/cards/{id}` na profilu `public` (2 vCPU / 4 GB); wynik i wąskie gardła w `.house/reports/load.md`; dodaj cache tam, gdzie trzeba.
5. **Tryb ciemny v3.** Przejrzyj hero, kafle, klastry, rolki i loader w ciemnym motywie; popraw gradienty i kontrast.
6. **Scenariusz demo (5 min) i pitch (zaległe z #24).** Skrypt kliknięć: wejście → granica Polski się rysuje → „Dopasuj w 30 s” jako samorząd z Pomorza → wynik → strona pomysłu → specyfikacja wdrożenia → przełączenie na inwestora → portfel i memo PDF → klastry „AI w zdrowiu”. Pitch PDF ≤ 10 slajdów z prawdziwymi liczbami z `/api/insights` i kosztem z README. Lektor (ElevenLabs) zrobimy później: przygotuj tylko tekst narracji.

## Zasady
Bez nowego frameworka; jedna rodzina ikon (Lucide); każda grafika AI oznaczona; `prefers-reduced-motion` respektowane; nic nie może przewijać się poziomo na 375 px.

## Gotowe, gdy
CI z Playwright i axe jest zielone; raport Lighthouse i load test są w repo; scenariusz demo i pitch są w `docs/`.
