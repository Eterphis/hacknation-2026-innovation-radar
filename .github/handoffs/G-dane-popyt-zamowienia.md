---
title: "[Runda 3 · D] Prawdziwe IP i spółki, popyt samorządów, teczka zamówienia, kalendarz naborów"
labels: [data, business, handoff]
---
**Dla:** czwartej osoby (dane + backend). Wklej agentowi całość.

## Najpierw przeczytaj
- `docs/stack.md`: technologie i modele (Basal bez LLM, Bielik 1.5B na CPU, router LLM, RabbitMQ + Celery, Postgres + Alembic, FastAPI, SPA bez frameworka).
- `docs/sciezki-uzytkownikow.md`: 6 ścieżek użytkowników i pomysły na wartość biznesową.
- `app/radar/business.py` (wycena), `app/radar/investor.py` (sygnały dla inwestora), `app/radar/api/deals.py` (memo, wdrożenia, alerty, API v1), `app/radar/api/clusters.py`.

## Zadania (od największej wartości)
1. **Patenty naprawdę (zaległe z #22).** EPO OPS (darmowy klucz) i/lub UPRP: dla organizacji z rejestru (`organizations`) pobierz zgłoszenia i patenty, zapisz w nowej tabeli `ip_assets` (migracja `0005`), powiąż z rekordem, gdy tytuł/słowa kluczowe pasują. `investor.signals().ip` ma brać dane z tabeli, a tekst opisu zostaje jako fallback. Cache na dysku, `optional: true`, testy na fixture'ach.
2. **Spółki i spin-offy (zaległe z #22).** API Otwarte KRS (po numerze KRS z rejestru RAD-on/REGON): spółki celowe uczelni i instytutów, kapitał, data, PKD. `investor.signals().commercial` z prawdziwego rejestru.
3. **Plik GUS (zaległe z #20/#22).** Załóż darmowy klucz BDL, uruchom `scripts/fetch_gus_adopters.py`, zacommituj `app/radar/data/adopters.json`. Sprawdź, że karty pokazują „GUS BDL” zamiast „szacunek”.
4. **Popyt samorządów (mapa popytu vs podaży).** Anonimowo zapisuj zagregowane profile z kreatora (rola, województwo, sektory, budżet; bez identyfikatorów, tylko liczniki per dzień) w tabeli `demand_signals`. Endpoint `GET /api/demand?sector=` → per województwo: popyt (profile + zapisy + polubienia) vs podaż (pomysły). To jest sygnał dla wykonawców i inwestorów.
5. **Teczka zamówienia publicznego.** `GET /api/cards/{id}/procurement`: opis przedmiotu zamówienia, kryteria oceny ofert (cena / jakość / czas), szacunkowa wartość (z `business_case`), lista potencjalnych wykonawców (`investor.implementers`) i właściwy tryb (próg zamówień). Wersja do druku jak memo. Bez nowych faktów: tylko pola już policzone.
6. **Kalendarz naborów.** Źródło naborów (FENG, FERS, FEnIKS, programy regionalne: listy naborów na funduszeeuropejskie.gov.pl lub RSS) → tabela `calls` z terminami; w karcie „Najbliższe nabory dla tego pomysłu” z dopasowaniem po sektorze, typie instytucji i województwie.
7. **Ocena społeczności 2.0.** Obok polubień licz zapisy (anonimowy beacon `POST /api/cards/{id}/signal {kind: save|deal|compare}`) i pokaż „Na fali w Twoim województwie” (`/api/trending?voivodeship=`).

## Zasady
Deterministycznie, bez LLM w ścieżce zapytania; każde nowe pole ma źródło i datę; brak klucza nie wywraca potoku; nowe tabele przez Alembic (zaktualizuj test głowy migracji); `pytest` zielony; żadnych danych osobowych.

## Gotowe, gdy
Karty z NCBR/RAD-on mają prawdziwe `ip`/`commercial` tam, gdzie są w rejestrach; `adopters.json` jest w repo; `/api/demand`, `/api/cards/{id}/procurement`, nabory w karcie działają na prawdziwych danych; testy przechodzą.
