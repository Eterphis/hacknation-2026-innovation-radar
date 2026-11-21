---
title: "[Handoff B] Małe modele na CPU i pregeneracja treści, domknięcie #7, publiczny URL dla jury"
labels: [ocena, ops, handoff]
---
**Dla:** kk3k02 (agent z #7). Wklej agentowi całość.

## Stan
- Twój PR #11 (agent z narzędziami, ewaluacja, metryki, Alembic, CI z k3d) jest otwarty. Przed merge zrób rebase na `main`: od tamtej pory doszły widoki odbiorców i wycena (`app/radar/business.py`) oraz naprawa grafu.

## Zasada kosztów (od właściciela projektu)
Treść, którą da się wygenerować wcześniej, ma być wygenerowana raz i trzymana statycznie. Nowe rekordy obsługują **małe modele na vCPU**, a nie wielomiliardowe modele w chmurze. Duże modele najwyżej jako opcja, nigdy domyślnie.

## Zadania
1. Zmerguj #11 (po rebase, z zielonym CI).
2. **Pregeneracja.** Komenda `radar pregenerate`, która dla gotowych kart liczy raz i zapisuje w bazie: brief do rolek, hasło, wycenę i dopasowanie do odbiorców. Ma działać przy imporcie partii danych i w nocy z beat. API tylko czyta.
3. **Mały model dla nowych rekordów:** Bielik 1.5B Q8 przez `docker compose --profile local-llm` (llama.cpp, CPU).
   - Zmierz czas i jakość na 30 rekordach i zapisz wynik w `.house/experiments.csv`.
   - Jeśli 1.5B jest za słaby, sprawdź Qwen2.5-1.5B albo 3B Q4.
   - Router: `local`, potem reguły; chmura tylko po jawnym włączeniu.
4. **Panel kosztów** w Grafanie: liczba wywołań LLM na dostawcę, szacunkowy koszt, procent rekordów obsłużonych bez LLM.
5. **Publiczny URL dla jury:** k3d albo VPS za tunelem. Tryb demo działa bez kluczy. Sprawdź z innego urządzenia i innej sieci.

## Gotowe, gdy
- Ponad 90% kart obsługiwanych bez dużego LLM.
- Średni czas obsługi nowego rekordu na 4 vCPU poniżej 5 s.
- Publiczny URL działa z telefonu.
