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

## Q-001 [open] Koncepcja produktu: Radar Innowacji „w obie strony”
- **Kontekst:** Treść zadania zostawia formę otwartą. Propozycja w `.house/PLAN.md` §1: platforma a→e (wykryj/zgłoś → karta → jawna ocena + podobne → ścieżka i dopasowania → mierniki), z wyróżnikiem: instytucje zgłaszają też problemy, a radar łączy je z rozwiązaniami.
- **Opcje:** A) koncepcja z PLAN §1 B) tylko narzędzie dla operatora (PCI), bez zgłaszania problemów C) inna (opisz)
- **Rekomendacja:** A, bo pokrywa wszystkie 6 „mile widzianych” mechanizmów i daje wyróżnik do pitchu.
- **Blokuje:** T001
- **Poziom:** krytyczny
- **Termin:** 2026-11-21 12:00
- **Domyślnie:** A
- **Odpowiedź:** —

## Q-002 [open] Stos technologiczny i dostawca LLM
- **Kontekst:** PLAN §2: Python 3.12 + FastAPI + SQLite + BM25, frontend Vite/React/TS/Tailwind, LLM przez oficjalne SDK `anthropic` (`claude-opus-5-5`, wymienialny adapter, tryb demo bez klucza), jeden kontener.
- **Opcje:** A) stos z PLAN §2 B) jeden Next.js (TypeScript) na całość C) inny (opisz)
- **Rekomendacja:** A, bo dane i ocena są wygodniejsze w Pythonie, a tryb demo chroni przed awarią klucza u jury.
- **Blokuje:** T001, T003, T009
- **Poziom:** krytyczny
- **Termin:** 2026-11-21 12:00
- **Domyślnie:** A
- **Odpowiedź:** —

## Q-003 [open] Pytania do PCI (mentorzy, Discord wyzwania)
- **Kontekst:** Niespójności w regulaminie zadania i rzeczy, których dokumenty nie mówią.
- **Opcje:** pytania do zadania: 1) próg nagrody „50% … tj. 2,5 pkt” przy max 25 pkt (§3 ust. 11 vs §2 ust. 5); 2) do pitchu przechodzą 3 zespoły (regulamin zadania) czy 5 (regulamin wydarzenia), czy jest Q&A; 3) czy wolno użyć płatnych API LLM i kodu sprzed wydarzenia; 4) czy PCI ma prawdziwe przykłady innowacji z regionu do demo; 5) czy film może być na YouTube; 6) kto docelowo prowadziłby radar.
- **Rekomendacja:** zadać 3, 4 i 6 od razu (wpływają na zakres), resztę przy okazji.
- **Blokuje:** nic
- **Poziom:** zawsze człowiek
- **Domyślnie:** —
- **Odpowiedź:** —
