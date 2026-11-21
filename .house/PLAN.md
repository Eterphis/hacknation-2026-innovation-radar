# Plan działania: Radar Innowacji (HackNation 2026, zadanie PCI)

Plan wykonawczy na 24 h (sob 21.11 11:00 → nd 22.11 11:00), pisany tak, żeby Claude Code mógł go wykonywać
zadanie po zadaniu. Źródła: pełna treść zadania i regulamin zadania (PDF od PCI), `spec.yaml`,
`playbooks/build.md`. Analiza zadania: dokument „PCI — analiza zadania konkursowego i plan działania”.

---

## 0. Jak to uruchomić z Claude Code

Wszystko startuje z katalogu głównego repo (`claude` w terminalu albo zakładka Code w aplikacji).

| Chcesz… | Wpisz w Claude Code |
|---|---|
| Wziąć następne gotowe zadanie z grafu | `/radar next` |
| Wykonać konkretne zadanie | `/radar T004` |
| Zobaczyć stan wszystkich zadań i co blokuje | `/radar status` |
| Puścić kilka niezależnych zadań naraz | `/radar wave 2` (odpala zadania fali 2 w osobnych worktree, max 3) |
| Ocenić build względem kryteriów jury | `/radar judge` |
| Pracować przez pełny system house | `/house-start` (repo główne, zob. README), potem `house night radar-innowacji` |

**Aplikację uruchamia się zawsze jedną komendą** (od T001, na każdym etapie, także u jury):

```
docker compose up --build        # http://localhost:8000, bez klucza działa tryb demo
docker compose run --rm app test # testy backendu w tym samym obrazie
```

Klucz LLM jest opcjonalny: `cp .env.example .env` i wpisz `ANTHROPIC_API_KEY`. Jedyne wymaganie na maszynie
to Docker (Docker Desktop na Windows/macOS); Python i Node nie są potrzebne do uruchomienia.

Komenda `/radar` jest w [`.claude/commands/radar.md`](../.claude/commands/radar.md). Każde zadanie to plik
`.house/tasks/T###-*.md` z celem, kontekstem, zakresem i **kryteriami akceptacji jako komendami**, więc
„gotowe” sprawdza maszyna, a nie deklaracja agenta.

Przed pierwszym zadaniem: odpowiedz na **Q-001** i **Q-002** w [`QUESTIONS.md`](QUESTIONS.md) (koncepcja i stos).
Domyślne odpowiedzi są wpisane, więc praca rusza nawet bez odpowiedzi, a decyzja trafia do `DECISIONS.md`.

---

## 1. Koncepcja produktu (propozycja do Q-001)

**Radar Innowacji** to otwarta platforma dla instytucji publicznych i operatora regionalnego (np. PCI), która
prowadzi każdą innowację przez pięć kroków z treści zadania:

1. **Wykryj albo zgłoś.** Formularz „opisz własnymi słowami” (2 minuty) + automatyczny radar, który czyta
   publiczne źródła (aktualności szkół i gmin, BIP, repozytoria uczelni, listy projektów NCBR i Interreg) i
   proponuje kandydatów na innowacje.
2. **Uporządkuj.** AI buduje **Kartę innowacji** w jednym schemacie dla każdego typu instytucji i innowacji
   (technologicznej, organizacyjnej, edukacyjnej, społecznej, procesowej). Człowiek poprawia, każde pole ma źródło.
3. **Oceń.** Jawna **karta oceny**: 6 kryteriów 1–5 z opisanymi poziomami. AI proponuje ocenę z cytatem
   dowodu, człowiek zatwierdza. Obok: **podobne rozwiązania** z patentów, publikacji, projektów i własnej bazy
   (ryzyko dublowania).
4. **Skieruj.** Silnik **ścieżek** (transfer dobrej praktyki, komercjalizacja, grant, akceleracja w PCI,
   pilotaż u partnera) i **dopasowanie odbiorców** z bazy potrzeb i podmiotów, każde z uzasadnieniem.
5. **Uzasadnij i mierz.** Rekomendacja z kluczowymi powodami, następnym krokiem i **miernikami
   skuteczności** (per innowacja i dla całego radaru).

Wyróżnik (do pitchu): radar działa **w obie strony**. Instytucje zgłaszają też *problemy*, a system łączy je z
innowacjami, które już gdzieś je rozwiązały. „Ten sam problem zgłosiło 12 gmin; gmina X go rozwiązała.”

Zasady, które jury zobaczy w każdym ekranie: **przejrzystość** (każda ocena ma kryterium, poziom, dowód i
źródło), **człowiek decyduje** (AI proponuje), **działa bez klucza** (tryb demo na nagranych danych).

---

## 2. Architektura i stos (propozycja do Q-002)

```
            ┌──────────────── web/ (Vite + React + TS + Tailwind) ────────────────┐
            │ Zgłoś · Radar (lista + mapa) · Karta · Ocena · Ścieżka · Panel      │
            └───────────────────────────────┬─────────────────────────────────────┘
                                            │ REST (JSON, schemat z app/radar/models.py)
┌───────────────────────────── app/ (Python 3.12 + FastAPI) ───────────────────────────┐
│ ingest/form ──► ingest/extract (LLM) ──► Karta ──► similarity ──► scoring ──► pathways │
│ ingest/detect (źródła publiczne)            │          (BM25 + opc.     (rubryka   matching│
│                                             ▼           embeddingi)      YAML)     metrics │
│                                  store (SQLite / JSON seed)                               │
│ llm.py: adapter  ── anthropic (claude-opus-5-5, structured outputs)                       │
│                  └─ demo (odtwarza nagrane odpowiedzi z data/recorded_llm/)               │
└──────────────────────────────────────────────────────────────────────────────────────────┘
data/seed/      innowacje, odbiorcy i potrzeby, korpus porównawczy (z adresami źródeł)
```

- **Backend:** Python 3.12, FastAPI, Pydantic v2 (kontrakt), SQLite przez `sqlite3` (bez ORM), `rank_bm25`
  do podobieństwa (embeddingi opcjonalnie), PyYAML dla rubryki. Wszystko na licencjach zgodnych z EUPL-1.2
  (MIT / BSD / Apache-2.0).
- **LLM:** oficjalne SDK `anthropic`, model `claude-opus-5-5` (zmienna `RADAR_MODEL`), structured outputs
  (`client.messages.parse` z modelem Pydantic), adaptive thinking, `effort` ustawiony jawnie (`low` dla
  ekstrakcji i klasyfikacji, `medium` dla oceny), server-side fallback przy odmowie. Adapter jest
  wymienialny: `RADAR_LLM=anthropic|demo`. Bez klucza aplikacja przechodzi w tryb demo z widoczną etykietą.
- **Frontend:** Vite + React + TypeScript + Tailwind; typy generowane ze schematu JSON kontraktu.
- **Uruchomienie: Docker od pierwszego commita.** Jeden wieloetapowy `Dockerfile` (etap `web`: Node buduje
  frontend; etap `app`: Python 3.12 slim + zbudowany frontend serwowany przez FastAPI) i `docker-compose.yml`
  z usługą `app` (port 8000, `env_file: .env` opcjonalny, wolumen `radar-data` na bazę SQLite,
  `healthcheck` na `/health`). Ten sam obraz idzie na publiczny URL (Render / Fly / Railway, decyzja w T010),
  więc „działa u mnie” = „działa u jury”. Dane demo i nagrania LLM są w obrazie, więc kontener startuje
  offline i bez klucza.
- **Tryb deweloperski (opcjonalny):** `docker compose -f docker-compose.yml -f docker-compose.dev.yml up`
  montuje kod i włącza przeładowanie (uvicorn `--reload`, Vite dev server na 5173).
- **Wejścia obrazu:** `docker compose run --rm app test` (pytest), `... app seed` (przeładowanie danych
  demo), `... app keycheck` (sprawdzenie klucza); obsługuje je `docker/entrypoint.sh`.
- **Repo:** `app/` backend + testy, `web/` frontend, `data/` dane i nagrania LLM, `scripts/` narzędzia,
  `docs/` dokumentacja dla jury i wdrożenia, `pitch/` slajdy, scenariusz, film.

---

## 3. Rdzeń merytoryczny (to, co jury będzie sprawdzać)

### 3.1 Karta innowacji (kontrakt w T001)

Tytuł · problem · rozwiązanie · typ innowacji (tech / organizacyjna / edukacyjna / społeczna / procesowa) ·
instytucja (typ: szkoła / uczelnia / JST / inna publiczna; powiat, gmina) · twórcy (role, kontakt za zgodą) ·
etap (pomysł / prototyp / pilotaż / wdrożone / powielone) · efekty i dowody · koszty i zasoby · prawa
(kto jest właścicielem, czy można dzielić) · słowa kluczowe i dziedzina · źródła (URL, data, kanał:
formularz / wykrycie) · status w procesie.

### 3.2 Kryteria oceny innowacji (rubryka w `app/radar/scoring/rubric.yaml`, T006)

| Kryterium | Pytanie | 1 | 3 | 5 |
|---|---|---|---|---|
| Dojrzałość | Jak daleko od użycia? | pomysł | pilotaż z użytkownikami | wdrożone i działa ≥ 6 mies. |
| Zapotrzebowanie | Ile instytucji ma ten problem? | brak sygnału | kilka zgłoszeń / podobnych potrzeb | wiele potrzeb w bazie lub dane publiczne |
| Nowość | Czy już to ktoś zrobił? | identyczne istnieje | podobne, inna skala lub kontekst | brak podobnych w korpusie |
| Przenaszalność | Czy da się powielić gdzie indziej? | zależne od lokalnych warunków | wymaga adaptacji | gotowy pakiet, niski koszt |
| Wpływ | Jakie mierzalne efekty? | brak danych | efekty opisane jakościowo | efekty zmierzone liczbowo |
| Gotowość twórców | Czy twórcy chcą i mogą dzielić? | nieznana | zgoda na kontakt | prawa jasne, chęć wdrożeń |

Każda ocena = poziom + uzasadnienie + cytat dowodu + źródło + pewność. Brak danych = jawne „brak danych”,
a nie zgadywanie. Wagi zależą od ścieżki, więc ta sama karta może być świetna do transferu i słaba do
komercjalizacji, i system to pokazuje.

### 3.3 Ścieżki (silnik w T007)

| Ścieżka | Kiedy | Następny krok | Odbiorcy |
|---|---|---|---|
| Transfer dobrej praktyki | wysoka przenaszalność i zapotrzebowanie, niskie bariery praw | pakiet wdrożeniowy, webinar dla instytucji z tym samym problemem | szkoły, JST, instytucje z bazy potrzeb |
| Komercjalizacja (licencja / spin-off) | technologia, nowość ≥ 4, prawa po stronie uczelni | rozmowa z centrum transferu technologii, analiza patentowa | firmy, inwestorzy, CTT |
| Rozwój z grantem | dojrzałość ≤ 3, wpływ obiecujący | dopasowany nabór (np. FEPK, NCBR, Interreg) | instytucje grantowe, partnerzy konsorcjum |
| Akceleracja / prototypowanie w PCI | twórcy 16–30 lat lub prototyp do zbudowania | zgłoszenie do programu PCI, laboratoria | PCI, mentorzy |
| Pilotaż u partnera | gotowe rozwiązanie, potrzeba u konkretnego odbiorcy | umowa pilotażowa 3 mies. | dopasowany odbiorca |
| Doprecyzuj | za mało danych do oceny | lista brakujących pól, prośba do twórcy | twórca |

Regułę wyboru ścieżki da się wydrukować (`GET /innovations/{id}/pathway?explain=1`), więc rekomendacja jest
odtwarzalna i nie jest czarną skrzynką.

### 3.4 Mierniki skuteczności (krok e, T007)

- **Per innowacja:** oczekiwane w 90 dni: liczba kontaktów z dopasowanymi odbiorcami, pilotaże, wnioski
  grantowe; status kroków ścieżki.
- **Dla radaru:** liczba wykrytych i zgłoszonych innowacji, odsetek z oceną i ścieżką, mediana czasu od
  zgłoszenia do pierwszego dopasowania, liczba dopasowań potrzeba↔innowacja, wykryte dublowania,
  wdrożenia poza miejscem powstania.

---

## 4. Harmonogram

| Godzina | Cel | Zadania | Punkt kontrolny |
|---|---|---|---|
| sob 11:00–12:00 | Decyzje i kontrakt | Q-001, Q-002, T001 | szkielet repo, LICENSE, kontrakt zielony, `docker compose up` odpowiada na `/health` |
| 12:00–15:00 | Fala 2: dane, LLM, UI na makietach | T002, T003, T009 | UI klikalne na danych z fixtures |
| 15:00–18:00 | Fala 3: wejście i podobieństwo | T004, T005 (+T009) | **18:00: pełny przepływ a→e z makietami, sprawdzony z innego urządzenia** |
| 18:00–22:00 | Fala 4: ocena, ścieżki, API | T006, T007, T008 | 2 przypadki z demo-flow przechodzą przez API |
| 22:00–00:00 | Fala 5: deploy i dokumentacja | T010, T012 | publiczny URL, tryb demo bez klucza |
| **00:00** | Runda sędziego | `/radar judge` | wybór funkcji „wow” (D-###) |
| 00:00–06:00 | Fala 6: wow + testy E2E | T013, T011 | Playwright zielony na URL produkcyjnym |
| 06:00–09:30 | Szlif UX, drugi przypadek, nagrania | poprawki, T014 start | zrzuty ekranu, nagranie zapasowe |
| **09:30** | Zamrożenie funkcji | tylko błędy | film, PDF, README, opis gotowe |
| **10:30** | Zgłoszenie na Hacktribe | T014 | otwarte z innego urządzenia |
| 11:00–14:45 | Próby pitchu | T014 | 3 pełne przebiegi 5 min |
| 14:45 / 15:15 | Wyniki etapu I / pitch | — | — |

---

## 5. Graf zadań

| Zadanie | Tytuł | Zależy od | Fala |
|---|---|---|---|
| [T001](tasks/T001-contract-skeleton.md) | Kontrakt danych i szkielet repo | — | 1 |
| [T002](tasks/T002-seed-data.md) | Dane demonstracyjne i korpus porównawczy | T001 | 2 |
| [T003](tasks/T003-llm-adapter.md) | Adapter LLM z trybem demo | T001 | 2 |
| [T009](tasks/T009-frontend.md) | Frontend: sześć ekranów przepływu | T001 | 2 |
| [T004](tasks/T004-intake-detect.md) | Zgłoszenie i automatyczne wykrywanie | T002, T003 | 3 |
| [T005](tasks/T005-similarity.md) | Wyszukiwanie podobnych i dublowania | T002 | 3 |
| [T006](tasks/T006-scoring.md) | Karta oceny z uzasadnieniem | T003, T005 | 4 |
| [T007](tasks/T007-pathways-matching.md) | Ścieżki, dopasowania i mierniki | T006 | 4 |
| [T008](tasks/T008-api-pipeline.md) | API i pełny pipeline | T004, T007 | 4 |
| [T010](tasks/T010-deploy-demo-mode.md) | Deploy, tryb demo, kontrola klucza | T008, T009 | 5 |
| [T012](tasks/T012-docs.md) | Dokumentacja dla jury i wdrożenia | T008 | 5 |
| [T011](tasks/T011-e2e.md) | Testy E2E dwóch przypadków | T010 | 6 |
| [T013](tasks/T013-wow.md) | Funkcja „wow” (wybór o 00:00) | T010 | 6 |
| [T014](tasks/T014-submission-pitch.md) | Zgłoszenie: PDF, film, opis, pitch | T011 | 7 |

Równolegle najwyżej 3 zadania (`spec.limits.max_parallel_agents`). Fala 2 to pierwsze miejsce, gdzie warto
odpalić trzy sesje naraz (`/radar wave 2`).

---

## 6. Jak to trafia w kryteria jury (etap I, 5 × 20%)

| Kryterium | Co pokazujemy | Dowód w demo |
|---|---|---|
| Związek z wyzwaniem | Pełny przepływ a→e z treści zadania, 5 typów innowacji, 4 typy instytucji | dwa przypadki w filmie i na żywo |
| Pomysł i oryginalność | Radar w obie strony (problemy ↔ rozwiązania), wykrywanie z publicznych tekstów, wagi zależne od ścieżki | ekran dopasowania „12 gmin ma ten problem” |
| Użyteczność i UX | Zgłoszenie w 2 minuty własnymi słowami, karta wypełnia się sama, jedno kliknięcie do rekomendacji | stoper w filmie |
| Kompletność prototypu | Działa na publicznym URL i lokalnie jedną komendą `docker compose up`, bez klucza w trybie demo, testy E2E | link + Playwright w README |
| Potencjał wdrożeniowy | Wiele organizacji (tenant = instytucja), API i eksport CSV, EUPL-1.2, opis RODO i bezpieczeństwa, plan po hackathonie | `docs/WDROZENIE.md`, slajd 9 |

Etap II (top 3, 5 min) ocenia tylko wystąpienie: spójność, jasność, zainteresowanie, pomysłowość
prezentacji, charyzmę. Pitch budujemy na historii jednej osoby (nauczycielka, urzędnik), nie na funkcjach.

---

## 7. Zasady obowiązujące wszystkie zadania

1. **Licencja.** Kod na EUPL-1.2 od pierwszego commita. Zależności tylko MIT / BSD / Apache-2.0 / LGPL / MPL.
   Dane tylko publiczne, z zapisanym źródłem, datą i warunkami użycia. Nic, co blokuje publikację w repo
   Ministerstwa Cyfryzacji (§4 ust. 8 regulaminu).
2. **Prawda w danych.** Przykłady fikcyjne mają w danych i w UI etykietę „Przykład”. Żadnych wymyślonych
   liczb w pitchu: każda liczba ma wiersz w `pitch/FACTS.md`.
3. **Klucze.** Nigdy w repo. `.env.example` pokazuje nazwy. Bez klucza działa tryb demo z etykietą.
4. **RODO.** Dane twórców tylko za zgodą (checkbox w formularzu), minimum pól, kontakt widoczny dopiero po
   zgodzie twórcy na dopasowanie.
5. **Przejrzystość AI.** Każde pole wypełnione przez AI ma źródło i znacznik „propozycja AI”; człowiek
   zatwierdza. Ograniczenia opisane w `docs/DANE_I_OGRANICZENIA.md` (wymóg z sekcji 5 treści zadania).
6. **Integracja codziennie.** Merge do `main` po każdym zadaniu, nie na końcu. Złota ścieżka zawsze działa.
7. **Raport po zadaniu.** `.house/reports/T###.md` + jedna linia w `PROGRESS.md`.
8. **Docker zawsze zielony.** Każde zadanie kończy się sprawdzeniem `docker compose up -d --build` +
   `/health` (+ smoke testem, gdy jest API). Nowa zależność trafia od razu do `Dockerfile` /
   `pyproject.toml` / `package.json`; nic nie może wymagać instalacji czegokolwiek poza Dockerem.
   Obraz ma być mały i szybki: `.dockerignore`, cache warstw zależności, start kontenera < 10 s.

---

## 8. Ryzyka i plan B

| Ryzyko | Sygnał | Plan B |
|---|---|---|
| Źródła publiczne bez API / blokują roboty | T002 nie ściąga danych w 45 min | ręcznie zebrany snapshot (CSV) z adresami źródeł; wykrywanie na zapisanych stronach |
| Klucz LLM nie działa u jury | keycheck czerwony | tryb demo na nagranych odpowiedziach, widoczna etykieta |
| Za szeroki zakres | o 18:00 brak pełnego przepływu | wyciąć wykrywanie automatyczne do 1 źródła, mapę do listy |
| Ocena AI niestabilna | te same dane → różne oceny | reguły deterministyczne jako baza, LLM tylko uzasadnienie; nagrane odpowiedzi w demo |
| Deploy pada przed jury | URL nie odpowiada | film 3 min + lokalny `docker compose up` w README + zrzuty ekranu |
| Docker na laptopie do pitchu nie działa | brak Docker Desktop / wirtualizacji | sprawdzić w sobotę wieczorem; obraz zbudowany wcześniej i zapisany (`docker save`), plan B: publiczny URL |
| Brak czasu na pitch | 09:30 bez slajdów | szablon slajdów z T014 gotowy od wieczora |

---

## 9. Checklista zgłoszenia (wymagania formalne, sekcja 4 treści zadania)

- [ ] Tytuł projektu
- [ ] Opis problemu i proponowanego rozwiązania
- [ ] Opis działania i głównych funkcji
- [ ] Prezentacja PDF, maks. 10 slajdów
- [ ] Film maks. 3 min w otwartym repozytorium (link), pokazujący działanie
- [ ] (opcjonalnie) repozytorium kodu, działający prototyp, zrzuty ekranu, link do demo, makiety
- [ ] Źródła danych, założenia i ograniczenia AI opisane (sekcja 5)
- [ ] Demo sprawdzone wg `protocols/demo-checklist.md`
- [ ] Zgłoszenie otwarte z innego urządzenia przed 10:30

---

## 10. Prompty startowe (gdy wolisz bez `/radar`)

Wklejasz w nowej sesji Claude Code w katalogu repo:

- **Fala 1:** `Przeczytaj .house/PLAN.md, .house/spec.yaml, .house/DECISIONS.md i .house/tasks/T001-contract-skeleton.md. Wykonaj T001 zgodnie z jego kryteriami akceptacji, na gałęzi task/T001-contract-skeleton. Na końcu uruchom wszystkie komendy z acceptance, napisz .house/reports/T001.md i dopisz linię do .house/PROGRESS.md.`
- **Dowolne zadanie:** to samo z innym numerem. Jeśli `depends_on` nie jest `merged` ani `done`, zatrzymaj się i powiedz, czego brakuje.
- **Sędzia:** `Jesteś sędzią. Oceń obecny build względem 5 kryteriów jury z .house/PLAN.md sekcja 6 (0–5, z dowodem: komenda, zrzut, liczba). Przejdź demo-flow.md na działającej aplikacji. Wypisz najtańszy sposób na +1 pkt w każdym kryterium. Zapisz .house/reports/judge-<n>.md.`
