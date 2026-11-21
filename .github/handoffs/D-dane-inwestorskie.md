---
title: "[Runda 2 · A] Dane klasy inwestorskiej: patenty, spółki, zespół, historia finansowania, porównywalne"
labels: [data, business, handoff]
---
**Dla:** agenta od danych (kontynuacja #12, po #18/#20). Wklej agentowi całość.

## Po co
Inwestor i wykonawca decydują, czy coś powstanie. Dziś karta pomysłu ma wycenę z reguł (`app/radar/business.py`: TAM/SAM/SOM, licencja, zwrot), ale opiera się tylko na tekście opisu. Inwestor zapyta: *kto za tym stoi, czy jest chronione, czy ktoś już na to dał pieniądze, ile warte były podobne rzeczy*. Ta runda ma dać na to odpowiedzi z prawdziwych, publicznych źródeł.

## Stan (main po #21)
- Harvester `radar/refresh.py` → `data/normalized/<id>.jsonl` → źródła `harvester-*` w `app/sources.yaml` → kolejka → workery.
- Rejestr organizacji RAD-on (`organizations`, migracja 0003), `resolve_org`, GUS BDL dla liczby odbiorców per województwo.
- Karta: `card_dict(full)` zwraca `business=business_case(rec, card)`; UI pokazuje to w sekcji „Model biznesowy i wycena”.

## Zadania (od największej wartości)
1. **Ochrona IP (patenty).** UPRP i EPO OPS (lub Espacenet/Lens jeśli łatwiej): dla organizacji i słów kluczowych pomysłu znajdź zgłoszenia/patenty, rodzinę, status, kraje. Zapisz jako encję `ip_assets` (z migracją 0004) powiązaną z organizacją i, gdy dopasowanie jest pewne, z pomysłem. W `business_case` dodaj `ip: {count, granted, families, countries, strength: none|weak|medium|strong}` i niech `success_probability` rośnie z siłą ochrony (jawne założenie w `assumptions`).
2. **Spółki i spin-offy.** KRS (API Otwarte KRS / rejestr.io jeśli darmowe) + REGON: dla uczelni/instytutów znajdź spółki celowe i spin-offy, kapitał zakładowy, datę, PKD. W karcie: „ścieżka komercjalizacji: spin-off istnieje (nazwa, KRS) / brak”. To kluczowe dla inwestora: z kim podpisać term sheet.
3. **Historia finansowania.** Z Kohesio, NCBR, CORDIS, OpenAIRE zsumuj, ile publicznych pieniędzy dostała organizacja i ten temat (kwota, programy, lata). `business_case.traction = {public_funding_pln, grants, last_year}`. Pokazuje, że ktoś już zweryfikował pomysł.
4. **Zespół.** ORCID/OpenAlex: autorzy, h-index, liczba wdrożeń/patentów, inne projekty. Tylko dane publiczne, bez danych kontaktowych osób prywatnych. `team = {people, top_h_index, prior_projects}`.
5. **Porównywalne (comparables).** Dla sektora i kosztu wdrożenia znajdź 3–5 podobnych, już zrealizowanych projektów (Kohesio/NCBR „zrealizowane”) z kwotą. Użyj ich jako kotwicy wyceny zamiast samych stałych `UNIT_PLN`; zostaw stałe jako fallback.
6. **Kalibracja.** Skrypt `scripts/calibrate_business.py` porównuje wyceny z reguł z comparables i wypisuje błąd per sektor; wynik zapisz w `.house/reports/calibration.md`.

## Zasady
- Bez LLM w tej ścieżce; wszystko deterministyczne, z cache na dysku (żeby demo działało offline).
- Każde nowe pole ma jawne źródło i datę (`provenance`), a UI może je pokazać.
- Limity API: backoff, `optional: true` dla źródeł, które mogą nie odpowiadać; brak klucza nie wywraca potoku.
- Nowe tabele = migracja Alembic (head testowany w `tests/test_migrations.py`).
- Testy na fixture'ach (`app/tests/fixtures/`), bez sieci w CI.

## Gotowe, gdy
- Co najmniej 30% kart z rekordów NCBR/RAD-on ma `ip`, `traction` lub `spinoff` z prawdziwych danych.
- `GET /api/cards/{id}` zwraca nowe pola; `pytest` zielony; raport kalibracji w repo.
- Krótki opis w README: skąd każde pole i jak odświeżyć.
