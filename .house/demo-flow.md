# Demo flow: złota ścieżka (a→e) na dwóch przypadkach

Scenariusz z sekcji 6 treści zadania: a) wprowadzenie lub wykrycie, b) uporządkowanie, c) ocena,
d) odbiorcy i ścieżka, e) uzasadnienie i mierniki. Frontend (T009) buduje dokładnie te ekrany, testy E2E
(T011) je klikają, film i pitch (T014) je pokazują.

**Oba przypadki są fikcyjne** i w danych mają `example: true`, a w UI etykietę „Przykład”. Liczby poniżej to
wartości z danych demonstracyjnych (T002), nie fakty o prawdziwych instytucjach.

Demo w 3 zdaniach: *Pracownik PCI widzi na radarze innowację wykrytą w aktualnościach gminy i drugą,
zgłoszoną przez nauczyciela w 2 minuty. Dla każdej dostaje kartę, jawną ocenę z dowodami i listę podobnych
rozwiązań. Na końcu widzi rekomendowaną ścieżkę, dopasowanych odbiorców i mierniki, po których pozna, czy
transfer się udał.*

---

## Przypadek 1 (UC1): wykrycie automatyczne, innowacja organizacyjna w gminie

Wejście: `data/seed/use_cases/uc1.html`, aktualność „Gminy Przykładowo” o aplikacji do zgłaszania awarii
oświetlenia ulicznego (zdjęcie + pinezka na mapie + SMS zwrotny), czas naprawy spadł z 14 do 5 dni.

| # | Krok użytkownika | Ekran po kroku |
|---|---|---|
| 1 | Otwiera **Radar**, klika „Uruchom skan źródeł” | Lista nowych kandydatów z kanałem „wykryte”, źródłem i pewnością; UC1 na górze |
| 2 | Klika kandydata UC1 → „Utwórz kartę” | **Karta innowacji**: problem, rozwiązanie, typ = organizacyjna/procesowa, instytucja = JST, etap = wdrożone, efekt „14 → 5 dni”; każde pole z ikoną źródła (podświetla zdanie w oryginale) i znacznikiem „propozycja AI” |
| 3 | Poprawia jedno pole, klika „Zatwierdź kartę” | Karta ma status „zweryfikowana”, w historii widać zmianę człowieka |
| 4 | Klika **Ocena** | 6 kryteriów z poziomem 1–5, uzasadnieniem i cytatem: dojrzałość 4, zapotrzebowanie 5 (8 gmin z potrzebą w bazie), nowość 2, przenaszalność 5, wpływ 4, gotowość twórców 3. Panel **Podobne**: 3 podobne rozwiązania z korpusu z wynikiem podobieństwa i linkiem |
| 5 | Klika **Ścieżka** | Rekomendacja: **Transfer dobrej praktyki**, z 3 powodami (wiązanymi z kryteriami), następnym krokiem „pakiet wdrożeniowy + webinar” i przyciskiem „pokaż regułę” |
| 6 | Przewija do **Dopasowania** | 8 gmin, które zgłosiły ten sam problem, posortowane wg dopasowania, każda z uzasadnieniem; przycisk „Zaproś do webinaru” (tylko oznacza, nic nie wysyła) |
| 7 | Otwiera **Panel** | Mierniki: oczekiwane w 90 dni (kontakty, pilotaże) oraz liczniki radaru (wykryte, ocenione, dopasowania, dublowania) |

## Przypadek 2 (UC2): zgłoszenie przez formularz, innowacja technologiczna ze szkoły

Wejście: `data/seed/use_cases/uc2.txt`, opis nauczyciela technikum (5–6 zdań, potocznie): uczniowie
(17–19 lat) zbudowali czujnik CO₂ do klas z sygnałem „przewietrz”, działa w 6 salach od 3 miesięcy.

| # | Krok użytkownika | Ekran po kroku |
|---|---|---|
| 1 | Otwiera **Zgłoś**, wkleja opis, zaznacza zgodę na kontakt, klika „Wyślij” | Postęp „porządkuję…”, po kilku sekundach karta |
| 2 | Widzi **Kartę**: typ = technologiczna + edukacyjna, instytucja = szkoła, etap = pilotaż, twórcy = uczniowie 17–19 lat | Brakujące pola oznaczone („koszt jednostkowy: brak danych”) z prośbą o uzupełnienie |
| 3 | Uzupełnia koszt, zatwierdza | Karta zweryfikowana |
| 4 | **Ocena** | Dojrzałość 3, zapotrzebowanie 4, nowość 3 (panel **Podobne** pokazuje publikację i patent o podobnym czujniku, ostrzeżenie „podobne istnieje: różnica w zastosowaniu szkolnym i koszcie”), przenaszalność 4, wpływ 3, gotowość 4 |
| 5 | **Ścieżka** | Rekomendacja: **Akceleracja / prototypowanie w PCI** (twórcy w wieku 16–30, prototyp do dopracowania) + druga opcja **Rozwój z grantem**; wagi ścieżek widoczne |
| 6 | **Dopasowania** | PCI (program i laboratoria), 2 firmy z branży wentylacji z bazy podmiotów, 3 szkoły z potrzebą „jakość powietrza w klasach” |
| 7 | **Panel** | Mierniki ścieżki: prototyp v2 w 60 dni, 3 szkoły pilotażowe, 1 rozmowa z firmą |

## Dane, których demo potrzebuje (T002)

- 2 wejścia przypadków (`uc1.html`, `uc2.txt`) + 6 stron‑fixtures dla skanu (w tym 2 strony, które NIE są
  innowacją, żeby pokazać filtrowanie).
- ≥ 24 karty innowacji w bazie (radar nie może być pusty), 5 typów innowacji, 4 typy instytucji.
- ≥ 20 odbiorców i potrzeb, w tym 8 gmin z potrzebą „awarie oświetlenia” i 3 szkoły z „jakość powietrza”.
- Korpus porównawczy ≥ 200 rekordów (patenty, publikacje, projekty) z adresem źródła; w nim podobne do UC1 i UC2.
- Nagrane odpowiedzi LLM dla UC1 i UC2 (`data/recorded_llm/`), żeby demo działało bez klucza.
