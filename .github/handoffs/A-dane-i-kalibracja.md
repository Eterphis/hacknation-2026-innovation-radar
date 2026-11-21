---
title: "[Handoff A] Dane: domknij #5 (PR), kalibracja wyceny prawdziwymi liczbami, więcej źródeł"
labels: [dane, handoff]
---
**Dla:** Michał (agent z #5). Wklej agentowi całość.

## Stan
- Gałąź `feat/issue5-live-sources` ma 9 commitów: rejestr organizacji z RAD-on, deduplikacja (wygrywa najpełniejszy rekord, Kohesio grupowane po programie), eksport crawlera, zapasowe źródło dla Interreg, poprawki TLS. **Brak PR.**
- `main` ma od niedawna wycenę biznesową regułami (`app/radar/business.py`) i widoki dla 6 grup odbiorców (`#/dla/<grupa>`, PR z gałęzi `feat/personas-business`).

## Zadania (kolejność)
1. Zrób rebase `feat/issue5-live-sources` na `main` i otwórz PR do #5. Testy obu pakietów muszą przechodzić.
2. **Kalibracja wyceny prawdziwymi danymi.** `ADOPTERS` w `app/radar/business.py` to dziś szacunki rzędów wielkości. Zastąp je liczbami z GUS BDL (gminy, szkoły, szpitale, biblioteki, firmy według PKD), także per województwo, żeby SAM był liczony dla regionu, a nie jako 1/16 kraju. Wynik zapisz jako `app/radar/data/adopters.json` z datą i źródłem. Liczby pobieraj jednorazowo skryptem, bez zapytań w runtime.
3. **Brakujące źródła:** OpenAlex (darmowy `OPENALEX_API_KEY` w `.env`; bez klucza był limit 429), Interreg (strona nie odpowiadała, sprawdź zapasowy plik XLSX), CORDIS, FE 2021–2027, UPRP (import ręcznego eksportu).
4. **Infrastruktura vs innowacja.** Filtr `is_infrastructure()` w `business.py` działa dziś tylko w widokach odbiorców. Przenieś tę regułę do Basala (`app/radar/basal/taxonomy.py`, powód odrzucenia „inwestycja infrastrukturalna”), żeby drogi, gazociągi i linie kolejowe nie trafiały do kolejki LLM.

## Zasady
Bez LLM w zbieraniu i normalizacji. Nie ruszaj `app/radar/api/static/*` (UI).

## Gotowe, gdy
- PR do #5 jest zmergowany.
- Widoki `#/dla/*` pokazują liczby odbiorców z GUS z datą.
- W bazie są rekordy z co najmniej 8 źródeł.
