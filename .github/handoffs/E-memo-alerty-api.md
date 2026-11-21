---
title: "[Runda 2 · B] Memo inwestycyjne z małego modelu, alerty dopasowań, API dla partnerów, publiczny URL"
labels: [llm, ops, business, handoff]
---
**Dla:** agenta od modeli i operacji (kontynuacja #13 i #11). Wklej agentowi całość.

## Po co
Inwestor nie czyta rolek, czyta memo. Wykonawca (firma, która wdroży rozwiązanie w gminie) chce dostać powiadomienie, gdy pojawi się coś, co może sprzedać. Ta runda zamienia radar w narzędzie pracy: dokument do wysłania, alert i API.

## Stan (main po #21)
- Agent oceny z narzędziami i walidacją cytatów (#11 — kk3k02 ma jeszcze 5 nowych commitów na `feat/assess-agent-ops`; najpierw je dokończ i zmerguj, `git merge-tree` z main jest czysty, uwaga na migrację 0003 przy „stamp by schema markers”).
- Personalizacja: `GET /api/match` (rola, województwo, sektory, budżet, cel) → dopasowanie % z uzasadnieniem; profil w `localStorage` (`radar-profile`).
- Profil `local-llm` (llama.cpp + Bielik 1.5B GGUF) w compose i Helm.

## Zadania
1. **Pregeneracja** (`radar pregenerate`): dla wszystkich gotowych kart wylicz raz i zapisz brief, business case, tagi, teksty rolek. Nowe rekordy idą przez mały model na CPU; duży model tylko z flagą. Licznik kosztu (tokeny, sekundy CPU) w `llm_calls` i w Grafanie.
2. **Memo inwestycyjne (1 strona PDF).** `GET /api/cards/{id}/memo.pdf`: problem, rozwiązanie, dojrzałość, rynek (TAM/SAM/SOM), wycena i założenia, IP/finansowanie (gdy dane z rundy A są), ryzyka i mitygacje z agenta, następny krok, źródła z linkami. Treść składana z gotowych pól (zero nowych faktów); mały model tylko wygładza zdania i ma walidację, że nie dodał liczb. Render bez przeglądarki (WeasyPrint lub reportlab), szablon w kolorach strony. Wariant dla wykonawcy: „specyfikacja wdrożenia” (zakres, koszt, harmonogram, kto kupuje, z jakiego programu).
3. **Watchlista i alerty.** Profil z `/api/match` zapisywany po stronie serwera pod anonimowym tokenem (bez logowania, bez e-maila w URL). Codziennie (beat) nowe pomysły z dopasowaniem ≥ 70% trafiają do skrzynki: RSS/Atom per token + opcjonalnie webhook. E-mail tylko jako adapter, domyślnie wyłączony.
4. **API dla partnerów.** `/api/v1/ideas`, `/api/v1/match`, `/api/v1/cards/{id}` z kluczem API, limitami (token bucket w Redis/DB), OpenAPI z przykładami. Eksport CSV/JSON dla funduszy i urzędów.
5. **Publiczny URL i koszt.** Najtańszy VPS (2 vCPU / 4 GB) z compose: Caddy z HTTPS, backup Postgresa, healthcheck. W README tabela kosztu miesięcznego: infrastruktura + LLM per 1000 nowych rekordów (z liczników z pkt 1). Cel: < 50 zł/mies. bez dużego modelu.
6. **Testy obciążeniowe** (locust): 50 rps na `/api/match` i `/api/ideas` na tym VPS, wynik w `.house/reports/load.md`.

## Zasady
- Memo i alerty działają bez żadnego klucza LLM (fallback na regułach).
- Żadnych danych osobowych w URL, logach ani alertach.
- Każdy nowy endpoint ma test; `pytest` i CI zielone; nowe tabele przez Alembic.

## Gotowe, gdy
- Z karty da się pobrać memo PDF (wersja inwestor i wykonawca), a zrzut PDF jest w `docs/screenshots/`.
- Profil z „Dopasuj radar” można zasubskrybować (RSS) i dostaje nowe pozycje po `reassess`.
- Aplikacja stoi pod publicznym adresem HTTPS; koszt jest opisany w README.
