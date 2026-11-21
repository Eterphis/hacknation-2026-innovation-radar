---
title: "[Dane] Wszystkie źródła na żywo → normalizacja → kolejka → workery (koniec trybu demo)"
labels: [dane, priorytet-1]
assignee_role: "Osoba A: dane i potok"
---
## Cel
Radar zbiera **pomysły z prawdziwych źródeł**, a nie zgłoszenia. Każde źródło z treści zadania i z notatki o danych jest podpięte, znormalizowane do jednego rekordu, wpada do RabbitMQ i jest ściągane przez workery Celery. Dane syntetyczne zostają tylko jako fallback dla jury.

## Zakres
1. **Jeden pakiet zamiast dwóch.** W repo są dwa pakiety o nazwie `radar`:
   - `app/radar`: potok, kolejka, Helm;
   - `radar/` w katalogu głównym: konektory z gałęzi `feature/pobieranie-danych` (`bibliotekanauki`, `openalex`, `radon`, `epo`, `cordis`, `fe_projects`, `interreg`, `ncbr`, `uprp_import`, crawler stron).

   Przenieść konektory do `app/radar/sources/connectors/` (albo przemianować pakiet główny na `harvester`). Dodać typ źródła `connector` w `app/radar/sources/registry.py`, który zamienia `radar.record/v1` na `Envelope`. Konektory adaptujemy, nie przepisujemy.
2. **Źródła na żywo w `app/sources.yaml`.** Każde dostaje `schedule_s`, limit zapytań i opis ograniczeń:
   - Biblioteka Nauki (już działa);
   - OpenAIRE `/projects` i `/researchProducts` (token z Secret);
   - Kohesio: eksport CSV dla PL i `/api/beneficiaries`;
   - RAD-on: projekty i instytucje;
   - EPO Linked Data i XML dokumentu;
   - CORDIS;
   - Fundusze Europejskie 2021–2027;
   - Interreg;
   - NCBR sukcesy;
   - crawler stron z `config/sites.json`.
3. **Normalizacja** do pól `Record` i `Signal v1` (`.house/reports/sources-and-idea-flow.md` §3): kwoty z polskim przecinkiem, daty, DOI, organizacje, województwo, prawa do treści.
4. **Rejestr organizacji (T023):** instytucje z RAD-on, ROR i Wikidata. Dzięki niemu Basal ma pewny `institution_type` i województwo.
5. **Dedup (T025):** rekordem kanonicznym jest najpełniejszy, a nie pierwszy przetworzony.
6. **Domyślnie `RADAR_DEMO_MODE=0`** w compose i Helm. Snapshoty w `app/samples/` z prawdziwych próbek, z atrybucją.

## Kryteria akceptacji
- [ ] `cd app && pytest` jest zielone, a testy kontraktu konektorów działają na fixture'ach, bez sieci.
- [ ] Po `docker compose up` co najmniej 6 źródeł pobiera prawdziwe rekordy przez worker `harvest`, co widać w panelu Operator → Źródła.
- [ ] Liczniki etapów się bilansują: przyjęte = gotowe + przegląd + odrzucone + w toku + DLQ.
- [ ] `.house/reports/data-access.md` jest zaktualizowany: każde źródło, sposób pobierania, częstotliwość, licencja, ograniczenia.

## Pliki
`app/radar/sources/*`, `app/sources.yaml`, `radar/sources/*` (przeniesienie), `app/radar/pipeline/tasks.py` (resolve_org, dedup). Nie ruszać `app/radar/api/static/*` (UI, Osoba B) ani `app/radar/pipeline/assess.py` (Osoba C).
