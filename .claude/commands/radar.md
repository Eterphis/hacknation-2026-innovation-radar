---
description: "Wykonuje plan Radaru Innowacji: następne zadanie, konkretne T###, falę, status albo rundę sędziego"
argument-hint: "next | T### | wave <n> | status | judge"
---

Pracujesz nad zadaniem konkursowym „Radar Innowacji” (HackNation 2026, PCI). Argument: `$ARGUMENTS`.

## Zawsze najpierw

1. Przeczytaj `.house/PLAN.md`, `.house/spec.yaml`, `.house/DECISIONS.md`, otwarte pytania w
   `.house/QUESTIONS.md`, `.house/demo-flow.md` i `.house/playbooks/build.md`.
2. Jeśli Q-001 lub Q-002 są `[open]` i minął ich `Termin`, przyjmij `Domyślnie`: oznacz pytanie
   `[answered <data>]` z odpowiedzią „domyślnie (judge)” i dopisz D-### do `DECISIONS.md`. Jeśli termin nie
   minął, a zadanie zależy od tego pytania, zapytaj człowieka jednym pytaniem i zaczekaj.
3. Jeśli w PATH jest `house` (system AI Software House), używaj `house check` / `house merge` zgodnie z
   `.house/playbooks/lifecycle.md`. Bez niego uruchamiaj komendy `acceptance` z pliku zadania sam.

## Tryby

**`next`**: znajdź w `.house/tasks/T*.md` pierwsze zadanie o `status: todo`, którego wszystkie
`depends_on` mają status `merged` albo `done`, w kolejności fal z PLAN §5. Wykonaj je jak w trybie `T###`.
Jeśli nic nie jest gotowe, powiedz, co blokuje (zadanie → brakująca zależność albo pytanie).

**`T###`**: wykonaj to jedno zadanie.
1. Sprawdź `depends_on`. Brakuje zależności → zatrzymaj się i powiedz której.
2. Ustaw w pliku zadania `status: doing`, `owner: claude`, `branch: task/T###-<slug>`; pracuj na tej gałęzi
   (utwórz ją z aktualnego `main`).
3. Zrób to, co mówi `Objective` i `Context`, nie ruszaj `Out of scope`. Nie zmieniaj plików z `protected`,
   chyba że to zadanie je tworzy (wtedy napisz je najpierw, potem kod).
4. Uruchom każdą komendę z `acceptance` (pole `run`), a gdy jest `expect`, sprawdź wyjście regexem.
   Napraw kod, aż wszystkie są zielone; nigdy nie osłabiaj testu ani kryterium. Kryteria `manual` opisz
   jako „do sprawdzenia przez człowieka/sędziego” z instrukcją.
5. Sprawdź Docker (PLAN §7 zasada 8), nawet gdy zadanie tego nie wymienia: `docker compose up -d --build`,
   `/health` odpowiada (a od T008 także `python scripts/smoke.py --url http://localhost:8000`), potem
   `docker compose down`. Każdą nową zależność dodaj do obrazu. Jeśli Docker nie działa na tej maszynie,
   napisz to w raporcie jako ryzyko, nie pomijaj po cichu.
6. Zapisz `.house/reports/T###.md` (po angielsku: co zrobione, wyniki komend, decyzje, ryzyka),
   dopisz jedną linię po polsku do `.house/PROGRESS.md`, ustaw `status: review`, zrób commit z opisem.
7. Nie scalaj sam do `main`, chyba że człowiek poprosi; zaproponuj scalenie.

**`wave <n>`**: weź zadania fali `<n>` z PLAN §5, które są gotowe, najwyżej 3 naraz
(`spec.limits.max_parallel_agents`). Dla każdego uruchom osobnego subagenta w osobnym worktree
(`isolation: worktree`) z poleceniem „wykonaj /radar T### według .claude/commands/radar.md”. Zbierz raporty,
podsumuj, zaproponuj kolejność scalania.

**`status`**: tabela wszystkich zadań (id, tytuł, status, właściciel, blokuje), otwarte Q-###, ostatnie 5
linii `PROGRESS.md`, ile czasu zostało do najbliższego punktu kontrolnego z PLAN §4 i do 10:30 w niedzielę.

**`judge`**: jesteś sędzią. Uruchom aplikację z czystego stanu przez `docker compose down -v && docker
compose up -d --build` (lub otwórz `.house/demo-url.txt`), przejdź oba przypadki z
`.house/demo-flow.md`, oceń build 0–5 w każdym kryterium jury z PLAN §6 z dowodem (komenda, zrzut, liczba),
przejdź `.house/protocols/demo-checklist.md`, wypisz najtańszy sposób na +1 punkt w każdym kryterium.
Zapisz `.house/reports/judge-<n>.md`. O północy dodatkowo wybierz funkcję „wow” z T013 i zapisz D-###.

## Zasady stałe (PLAN §7)

EUPL-1.2 i zgodne licencje zależności · dane tylko publiczne, ze źródłem · przykłady oznaczone „Przykład” ·
klucze nigdy w repo, tryb demo bez klucza · zgoda twórców przed zapisaniem kontaktu · każda wartość od AI
ze źródłem i do zatwierdzenia przez człowieka · złota ścieżka zawsze działa · aplikacja zawsze startuje
jedną komendą `docker compose up --build`, bez instalowania czegokolwiek poza Dockerem.
