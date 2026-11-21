# Pytania do człowieka

Otwarte pytania czekają na briefing („jak tam” / `/house-status`). Po odpowiedzi status zmienia się na
`[answered YYYY-MM-DD]`, a decyzja trafia do `DECISIONS.md`.

Format wpisu: nagłówek drugiego poziomu `Q-<kolejny numer, 3 cyfry> [open] <tytuł>`, pod nim:

```
- **Kontekst:** co się stało i dlaczego to pytanie
- **Opcje:** A) … B) …
- **Rekomendacja:** … (jednym zdaniem dlaczego)
- **Blokuje:** T### | nic
- **Poziom:** krytyczny | zawsze człowiek
- **Termin:** YYYY-MM-DD HH:MM (tylko krytyczny: po tym czasie judge przyjmuje „Domyślnie”)
- **Domyślnie:** A (rekomendacja; pusta = brak domyślnej)
- **Odpowiedź:** —
```

## Q-001 [answered 2026-11-21] Zatwierdzenie pól `proposed` w spec.yaml (intake z PDF-ów PCI)
- **Kontekst:** Intake z „Pełnej treści zadania” i „Regulaminu zadania konkursowego” PCI. Uzupełnione i oznaczone `proposed`: `goal_full`, `users`, `data_sources`, `contact`, `scoring.rubric` (etap I: 5 kryteriów po 20%, 0-5 pkt, max 25), `scoring.rubric_stage2` (pitch TOP 3), `scoring.winner`, `rules.allowed_ai`, `rules.allowed_autonomous_agents`, `rules.task_notes`, `deliverables.*` (film ≤ 3 min w otwartym repo, PDF ≤ 10 slajdów, teksty obowiązkowe, opis źródeł danych/założeń/ograniczeń AI, licencja EUPL-1.2, repo opcjonalne przy zgłoszeniu), komentarz przy kamieniu milowym 14:45 (TOP 3 zamiast TOP 5).
- **Opcje:** A) zatwierdzam wszystko B) zatwierdzam z poprawkami (wypisz) C) odrzucam
- **Rekomendacja:** A, bo każde pole jest wzięte wprost z paragrafu wskazanego w komentarzu.
- **Blokuje:** ideacja
- **Poziom:** krytyczny
- **Termin:** 2026-11-21 13:00
- **Domyślnie:** A
- **Odpowiedź:** A: zatwierdzam wszystko (człowiek, 2026-11-21 11:37), zob. D-001

## Q-002 [open] Pytania do PCI (stanowisko PCI / Discord wyzwania / k.moczarny@pcinn.org)
- **Kontekst:** Niespójności i luki w dokumentach PCI:
  1. Próg nagrody: §3 ust. 11 mówi „50% maksymalnej liczby punktów, określonej w §2 ust. 6, tj. 2,5 punktu”, a max to 25 pkt (§2 ust. 5). Czy próg to 12,5/25, czy średnia 2,5/5 na kryterium?
  2. TOP 3 (regulamin zadania §2 ust. 8) czy TOP 5 (regulamin wydarzenia)? Zakładamy TOP 3, bo regulamin zadania ma pierwszeństwo.
  3. Czy etap II ocenia wyłącznie pitch, czy wynik etapu I też się liczy?
  4. Czy wolno używać zewnętrznych API LLM (np. Claude) w prototypie i czy w demo dla jury wymagane jest działanie bez klucza/offline?
  5. Czy wolno użyć kodu/szablonów przygotowanych przed wydarzeniem (`starter_code_allowed`)?
  6. Czy film może być na YouTube (niepubliczny link), czy musi być w repo kodu?
  7. Czy są przykładowe przypadki innowacji od PCI do demo (min. 2 wymagane w §6)?
  8. Termin wypłaty „do X dni” (§3 ust. 5) i numeracja załączników (§5 ust. 6 wskazuje nr 2, lista ma wzór oświadczenia jako nr 1) — tylko do wiadomości.
- **Opcje:** A) zadaję pytania mentorom teraz B) pracujemy na założeniach z `rules.task_notes`, pytamy później
- **Rekomendacja:** A, bo pytania 1, 4 i 5 mogą zmienić wybór koncepcji i stosu.
- **Blokuje:** nic
- **Poziom:** zawsze człowiek
- **Termin:** —
- **Domyślnie:** —
- **Odpowiedź:** —
