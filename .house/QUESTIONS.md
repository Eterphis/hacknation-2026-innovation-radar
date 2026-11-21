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

## Q-003 [open] Wybór pomysłu (runda ideacji 1)
- **Kontekst:** 5 pomysłów z kartami prior-art i oceną wg rubryki etapu I (`reports/ideation-1.md`). Ranking: I-004 Paszport transferu 21/25, I-003 Giełda problem ↔ rozwiązanie 19, I-001 Radar z jawną oceną 18, I-002 Zwiadowca źródeł publicznych 16, I-005 Wywiad + mapa 15. Największe ryzyko oryginalności: EU Innovation Radar (ta sama nazwa i cel, ale tylko projekty UE) i OECD OPSI.
- **Opcje:** A) I-001 jako szkielet (scenariusz a-e) + I-004 jako wyróżnik; potem I-003, potem I-002 na jednym źródle B) I-001 + I-003 (giełda problemów jako wyróżnik) C) sam I-001 (najmniejsze ryzyko wykonania) D) inny wybór (opisz)
- **Rekomendacja:** A, bo daje szacunkowo 22/25 i odpowiada wprost na §9 treści („co dzieje się z innowacją po jej zidentyfikowaniu”), a scenariusz a-e i tak wymaga I-001.
- **Blokuje:** plan (tasks/T###), golden path na 18:00
- **Poziom:** krytyczny
- **Termin:** 2026-11-21 13:00
- **Domyślnie:** A
- **Odpowiedź:** zastąpione przez Q-004 po ustaleniu z mentorami (D-002), 2026-11-21 12:05

## Q-004 [answered 2026-11-21] Wybór pomysłu (runda ideacji 2, po ustaleniu z mentorami)
- **Kontekst:** Mentorzy: radar sam wyszukuje pomysły w bazach (np. z §7) i dalej je przetwarza (D-002). 5 nowych pomysłów z kartami prior-art i oceną (`reports/ideation-2.md`), dostęp do baz w `reports/data-access.md`. Ranking: I-009 Sprawdzone gdzie indziej 21/25, I-006 Lejek radaru 20, I-010 Zapytaj radar 20, I-007 Łańcuch dowodów 19, I-008 Uśpione patenty 17.
- **Opcje:** A) I-006 lejek jako szkielet + I-007 „lekki” (dojrzałość z dowodów) + paszport transferu (I-004/I-009) na wyjściu B) sam I-009 (tylko bazy projektów, transfer) C) I-006 + I-010 (lejek + pole „zapytaj radar”) D) inny wybór (opisz)
- **Rekomendacja:** A, bo szacunkowo 22/25, a ekran „dojrzałość z linkami do publikacji, patentu i brakującego wdrożenia” odpowiada na zarzut „to już istnieje” (EU Innovation Radar opiera się na ankietach).
- **Blokuje:** plan (tasks/T###), golden path na 18:00
- **Poziom:** krytyczny
- **Termin:** 2026-11-21 13:30
- **Domyślnie:** A
- **Odpowiedź:** — (korekta 13:28: wpis „domyślnie A” z 13:27 był przedwczesny, termin 13:30 jeszcze nie minął; D-004 nie obowiązuje). 13:36: zastąpione przez Q-007 (runda 3, D-006)

## Q-005 [open] Dostęp do baz: konta i licencje danych
- **Kontekst:** Z `reports/data-access.md`: EPO OPS wymaga darmowej rejestracji (konto zakłada człowiek, nie agent); UPRP API ma token albo listę IP, niejasne; PBN API wymaga klucza od OPI (nierealne w 24 h); keep.eu API wymaga klucza mailem, ale eksport CSV działa bez niego. Regulamin §4 ust. 8: dane z baz nie mogą blokować publikacji na EUPL.
- **Opcje:** A) zakładamy konto EPO OPS teraz; UPRP próbujemy jednym wywołaniem; Interreg/NCBR jako snapshot; w repo tylko mała próbka danych z podaniem źródła B) wszystko jako snapshot, bez kluczy C) inaczej (opisz)
- **Rekomendacja:** A, bo jedno źródło patentowe na żywo wzmacnia demo, a tryb snapshot i tak chroni przed awarią klucza u jury. Przy okazji zapytać mentorów, czy dane z tych baz wolno trzymać w repo na EUPL.
- **Blokuje:** zadania konektorów EPO i UPRP
- **Poziom:** zawsze człowiek
- **Termin:** —
- **Domyślnie:** —
- **Odpowiedź:** —

## Q-006 [answered 2026-11-21] Architektura (D-003): dwa doprecyzowania
- **Kontekst:** D-003: Helm/Kubernetes, workery z zabezpieczeniem przed pominięciem, RabbitMQ + Celery, podmienialne LLM z fallbackiem. Projekt w `reports/ideation-2.md`, sekcja „Architecture”.
  1. „Zabezpieczenie przed pominięciem sensu” rozumiem podwójnie: (a) żaden rekord nie ginie w kolejce (acks_late, idempotencja, retry, dead-letter, uzgadnianie liczników) oraz (b) wynik LLM jest sprawdzany, czy nie zgubił treści (schemat, cytat ze źródła dla każdego pola, inaczej `needs_review`).
  2. Gdzie działa Kubernetes na demo: lokalnie (k3d/kind) czy w chmurze z publicznym URL-em?
- **Opcje:** A) 1 = (a) + (b); 2 = docker compose jako ścieżka dla jury + Helm chart testowany na k3d, publiczny URL tylko jeśli starczy czasu B) 1 = tylko (a); 2 jak w A C) inaczej (opisz)
- **Rekomendacja:** A, bo (b) to jawność i kontrola jakości, o które pyta §5 treści, a compose daje jury działanie bez klastra.
- **Blokuje:** zadania workerów i wdrożenia
- **Poziom:** krytyczny
- **Termin:** 2026-11-21 13:30
- **Domyślnie:** A
- **Odpowiedź:** — (korekta 13:28: wpis „domyślnie A” z 13:27 był przedwczesny, termin 13:30 jeszcze nie minął; D-005 nie obowiązuje). 13:36: termin minął, obowiązuje domyślne A (D-005)

## Q-007 [open] Wybór pomysłu (runda ideacji 3: aplikacja webowa + agent AI, D-006)
- **Kontekst:** 5 pomysłów na to, co robi agent i jak tok rozumowania trafia do urzędnika (`reports/ideation-3.md`, karty prior-art I-011..I-015). Ranking: I-011 Agent-analityk z uzasadnieniem urzędowym 22/25, I-012 Agent na zlecenie urzędnika 20, I-014 Adwokat i recenzent 20, I-013 Radar ciągły 19, I-015 Karta-checklista 19. Wspólny szkielet: konektory → parsowanie → rejestry → łączenie → ocena → klasyfikacja „do czego i dla kogo” → wynik.
- **Opcje:** A) I-011 jako rdzeń + I-012 jako wejście („opisz potrzebę”) + jedno przejście recenzenta z I-014 + wynik w układzie karty z I-015 B) sam I-011 C) I-012 + I-011 bez recenzenta D) inny wybór (opisz)
- **Rekomendacja:** A, bo szacunkowo 23/25: uzasadnienie w układzie znanym urzędnikowi (ustalenia z dowodami → kryteria → ocena → co przemawia przeciw → rozstrzygnięcie → ograniczenia) jest wyróżnikiem i odpowiada na wszystkie cztery pytania z §2.
- **Blokuje:** plan (tasks/T###), golden path na 18:00
- **Poziom:** krytyczny
- **Termin:** 2026-11-21 14:15
- **Domyślnie:** A
- **Odpowiedź:** —
