---
title: "[UI] Interfejs na szablonie i komponentach: neumorfizm, mapa Polski, rolki, graf"
labels: [ui, priorytet-1]
assignee_role: "Osoba B: UI/UX"
---
## Cel
Czytelny, spójny interfejs zbudowany na **gotowym szablonie i bibliotece komponentów**, a nie generowany od zera. Pierwsza wersja jest w `app/radar/api/static/`: vanilla JS, tokeny neumorfizmu, ikony Lucide, mapa z granic województw. Zadanie: dopracować ją do poziomu produktu albo przenieść na szablon (np. Tabler albo shadcn/ui + Vite, budowany do `static/`).

## Zakres
1. **Design system:** neumorfizm (`designmd.app/library/neumorphism`), czyli promienie 14 i 28 px, miękkie podwójne cienie i jedno źródło światła.
   - Paleta: biel i czerwień jako akcent, czerń dla tekstu i kontrastu, beżowe tło sekcji.
   - Przełącznik trybu jasny / ciemny / systemowy, zapamiętywany między wizytami.
   - Logo w stylu ikony z App Store: 3D, efekt szkła.
2. **Ikony** tylko z jednego zestawu (Lucide, `static/icons.svg`), szare i kontrastowe. Jeśli informację da się pokazać tabliczką z ikoną, nie wypisujemy jej samym tekstem.
3. **Mapa Polski** z obrysem województw (`static/poland.json`):
   - wybór sektora;
   - kolor według liczby pomysłów;
   - zaznaczone luki;
   - kliknięcie województwa otwiera listę pomysłów;
   - podział widoków i zadań w kształcie Polski.
4. **Rolki** zbudowane z komponentów:
   - tabliczka lokalizacji z ikoną pinezki, np. „Rzeszów · podkarpackie”;
   - tabliczka budżetu z ikoną banknotu i zakresem;
   - dojrzałość jako pasek etapów;
   - typ instytucji jako ikona;
   - płynne animacje przewijania i polubienia (tylko transform i opacity, z obsługą `prefers-reduced-motion`).
5. **Graf:** kolory, wielkości i etykiety spójne z resztą UI, filtrowanie po hubach, legenda.
6. **Dostępność:** kontrast AA, widoczny fokus, obsługa klawiaturą, tabela zamiast wykresu na żądanie, ekran 375 px bez poziomego przewijania.

## Kryteria akceptacji
- [ ] Wszystkie zakładki działają w trybie jasnym i ciemnym; zrzuty z Playwright (desktop i 375 px) są w CI.
- [ ] Lighthouse daje co najmniej 90 punktów za dostępność.
- [ ] Jeden zestaw ikon, zero emoji i zero samego tekstu tam, gdzie wystarczy ikona z etykietą.

## Pliki
`app/radar/api/static/*` oraz ewentualny `app/ui/` z buildem. API zmieniamy tylko po uzgodnieniu z Osobą A lub C.
