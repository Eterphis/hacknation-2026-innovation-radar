---
title: "[Runda 2 · C] Lejek inwestora, porównanie, giełda wykonawców dla gmin, pitch"
labels: [ui, business, pitch, handoff]
---
**Dla:** agenta od UI i pitchu (kontynuacja #14). Wklej agentowi całość.

## Po co
Jury ma zobaczyć, że to narzędzie, z którego inwestor i wykonawca **korzystają codziennie**, a nie katalog. Trzy ekrany robią tę różnicę: lejek transakcji, porównanie i giełda „potrzeba gminy ↔ wykonawca ↔ pomysł”.

## Stan (main po #21)
- SPA bez frameworka: `app/radar/api/static/{index.html,app.js,app.css}`, routing hash (`#/`, `#/dla/<grupa>`, `#/dopasuj`, `#/mapa`, `#/odkrywaj`, `#/graf`, `#/rolki`, `#/zrodla`).
- Styl: neumorfizm, beż/biel/czerwień, ikony Lucide (sprite inline, `icon("nazwa")`), komponenty `plate`, `locPlate`, `moneyPlate`, `ring`, `stepper`, `avatar`, karta `openCard` z sekcją biznesową.
- „Dopasuj radar”: kreator 5 pytań → `/api/match` z % i uzasadnieniem.
- Higgsfield: 6 teł grup odbiorców w `static/hero/`. **Kredyty: zostało ok. 9.** Przed każdą generacją sprawdź koszt i saldo; najpierw tani model obrazów, wideo tylko na koniec.

## Zadania
1. **Lejek inwestora** `#/portfel`: kolumny Nowe → Kontakt → Due diligence → Term sheet → Odrzucone; przeciąganie (i klawiatura), notatka i data przy każdej karcie, suma wycen w kolumnie. Dane w `localStorage` teraz; interfejs gotowy na API z rundy B. Przycisk „Dodaj do portfela” w karcie i w wynikach dopasowania.
2. **Porównanie** `#/porownaj?ids=a,b,c`: 2–4 pomysły obok siebie: dojrzałość, koszt, TAM/SAM, wycena, zwrot, odbiorcy, finansowanie, ryzyka, IP (gdy dane z rundy A). Wyróżnij najlepszą wartość w wierszu. Na telefonie przewijane karty, nie tabela.
3. **Giełda wykonawców** `#/wdrozenia`: dla gminy/szkoły/szpitala: „moje potrzeby” (z kreatora, sektor + budżet + region) → gotowe pomysły do wdrożenia → kto może wdrożyć (organizacja autorska, spin-off, firmy z tego sektora w regionie z rejestru) → z jakiego programu sfinansować. Dla wykonawcy odwrotnie: „gdzie mogę to sprzedać”: mapa gmin z potrzebą + szacowany przychód. Backend: endpoint `GET /api/deployments?role=…` składany z istniejących danych (`business.py`, `organizations`, `insights`), bez LLM.
4. **Onboarding 3 kliknięcia**: pierwsza wizyta → wybór roli (kafle) → 2 pytania → od razu wynik dopasowania. Mierz czas do pierwszego wyniku (cel < 20 s).
5. **Pitch** (PDF ≤ 10 slajdów + film ≤ 3 min): historia „od artykułu w bazie do gminy, która wdraża, w 3 kliknięcia”, prawdziwe liczby z `/api/insights`, ekrany z zadań 1–3, koszt infrastruktury z rundy B. Grafiki z Higgsfield maks. 3 nowe; reszta to zrzuty aplikacji.
6. **Playwright w CI**: zrzuty desktop i 375 px, jasny i ciemny, dla wszystkich tras + test „3 kliknięcia do wyniku”.

## Zasady
- Szablon i komponenty istniejące; zero nowego frameworka. Jeden zestaw ikon (Lucide, szare, kontrastowe).
- Kontrast AA, pełna obsługa klawiatury, brak poziomego przewijania na 375 px.
- Każda grafika AI oznaczona „wizualizacja AI”.

## Gotowe, gdy
- Trasy `#/portfel`, `#/porownaj`, `#/wdrozenia` działają na prawdziwych danych; zrzuty w `docs/screenshots/`.
- Pitch PDF i film w repo lub w linkach w README; CI z Playwright zielone.
