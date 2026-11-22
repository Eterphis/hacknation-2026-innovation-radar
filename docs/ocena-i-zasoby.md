# Samoocena, zasoby i działanie na produkcji (22.11.2026, 02:00)

## 1. Ile punktów (etap I: 5 kryteriów × 0–5, wagi po 20%, maks. 25)

| Kryterium | Teraz | Co mamy | Co podnosi ocenę do 5 |
|---|---|---|---|
| Związek z wyzwaniem i jakość rozwiązania | **4,5** | pełna droga: wykrycie (12 źródeł + zgłoszenia + RSS) → Basal → karta z cytatami → ocena wg jawnych kryteriów → ścieżka → odbiorcy, partnerzy, wdrożenia | łańcuch dowodów publikacja ↔ projekt ↔ patent (etap `link` to dziś przejście bez zmian) |
| Pomysł i oryginalność | **4** | Basal bez LLM, wycena regułami (TAM/SAM/SOM z GUS), gotowość inwestycyjna, rolki, klastry „technologia × branża”, mapa przychodu dla wykonawcy | jedna wyraźna „funkcja wow” w pitchu (np. zgłoszenie jury → karta z wyceną w < 1 min na żywo) |
| Użyteczność i jakość doświadczenia | **4** | 6 ścieżek z kreatorem, strona pomysłu, zapisywanie, ocena społeczności, telefon, tryb ciemny, ładowanie z radarem nad Polską | testy z 2–3 osobami, dostępność (axe), opisy kart pisane ludzkim językiem przez model zamiast surowych pól |
| Kompletność prototypu i demonstracji | **3** | działa na prawdziwych danych (1692 rekordy), scenariusz a–e (`docs/scenariusz-walidacji.md`) | **film ≤ 3 min i PDF ≤ 10 slajdów są wymagane** i jeszcze ich nie ma; bez nich ok. 2–3 pkt |
| Potencjał wdrożeniowy i skalowalność | **4,5** | Helm + CI z k3d, kolejka z DLQ, obserwowalność, API dla partnerów z kluczami, token operatora, koszt < 50 zł/mies., RODO (bez danych osobowych) | **licencja EUPL-1.2 w repo (warunek wypłaty nagrody)**, publiczny adres demo |

**Szacunek: ok. 20 / 25 (80%) po dodaniu filmu i slajdów; bez nich ok. 17–18 / 25.** Próg nagrody to 50%. Do etapu II wchodzi TOP 3, a tam liczy się wyłącznie pitch (5 kryteriów prezentacji).

## 2. Modele i ile to liczy

| Element | Model | Zasoby | Szybkość (zmierzone lokalnie) |
|---|---|---|---|
| Klasyfikacja (wszystkie rekordy) | Basal: słowniki + prototypy + wyuczona głowa, embedding hashing 512-d | 1 rdzeń, < 100 MB | **~1 ms na rekord (~950 rekordów/s na rdzeń)** |
| Podobieństwo (opcjonalnie lepsze) | `intfloat/multilingual-e5-small` (ONNX, fastembed) | ~120 MB modelu, ~300 MB RAM | kilkadziesiąt tekstów/s na CPU |
| Karta i agent oceny dla nowych rekordów | Bielik 1.5B v3.0 Instruct GGUF Q8_0 (llama.cpp) | ~2 GB RAM, 4 vCPU | ~1 min na krok agenta; dla zgłoszeń wystarcza ścieżka regułowa (sekundy) |
| Fallback w chmurze (opcjonalnie) | Claude Sonnet 5.5 / model zgodny z OpenAI | 0 lokalnie | sekundy; płatne za token |
| Wycena, dopasowanie, wdrożenia, klastry, memo, alerty | reguły (bez modelu) | ułamki ms | natychmiast |
| Grafiki | Higgsfield `z_image`, wygenerowane raz (42 pliki, 1,5 MB WebP) | 0 w działaniu | statyczne |

Cała aplikacja bez LLM: **~1 GB RAM** (API 310 MB, worker ingest 210 MB, worker LLM 130 MB, RabbitMQ 160 MB, Postgres 80 MB, beat 70 MB). Z Bielikiem: VPS 4 vCPU / 8 GB. Bez GPU.

## 3. Jak jury doda pomysł i jak go wyłapiemy (bez przekraczania limitów)

1. **Formularz w aplikacji (`#/zglos`)**, bez konta. Zgłoszenie trafia do tego samego potoku z **najwyższym priorytetem w kolejce** (9 z 9). **Nigdy nie jest po cichu odrzucane:** jeśli Basal ma wątpliwości, karta i tak powstaje, a wątpliwości idą do operatora. Ekran pokazuje etapy na żywo i link do gotowej karty (`/api/submissions/{id}`).
2. **Webhook (`POST /api/ingest/webhook/zgloszenia`, podpis HMAC)** dla formularzy zewnętrznych (Google Forms przez Apps Script, Microsoft Forms / Typeform przez Make lub Zapier) i systemów instytucji.
3. **RSS/Atom dowolnej platformy** (strony uczelni, JST, gov.pl, blogi, kanały YouTube, mostki RSS dla profili społecznościowych). Adresy podajemy w `RADAR_RSS_FEEDS` (bez zmiany kodu). Odpytywane co 2 min **warunkowym GET** (`If-None-Match` / `If-Modified-Since`): niezmieniony kanał to jedna odpowiedź 304, bez pobierania i bez zużywania limitu. Do przetwarzania idą tylko nowe wpisy.
4. **Bazy publiczne** (NCBR, Kohesio, RAD-on, OpenAIRE, Biblioteka Nauki, CORDIS, OpenAlex, UPRP, EPO) pobierane przyrostowo (kursor `since`), z ponowieniem po `Retry-After`, zapisem kursora po każdej stronie i **blokadą nakładających się pobrań** jednego źródła. Każdy worker trzyma **minimalny odstęp między zapytaniami do jednego hosta**.
5. **Idempotencja:** `(źródło, id, hash treści)`; ponowne dostarczenie nic nie psuje, DLQ łapie błędy, liczniki „pobrane = przetworzone + DLQ” są w Grafanie.

Gdyby jury dodało pomysł na platformie bez API i bez RSS, operator wkleja link lub opis w formularz. Jeśli platforma ma eksport CSV lub JSON, zostaje on źródłem typu `snapshot` w `sources.yaml` (konfiguracja, nie kod).

## 4. Czy potrzebne są konta

- **Użytkownicy: nie.** Przeglądanie, dopasowanie, zapisywanie, portfel i polubienia działają bez konta: profil i zapisane pomysły są w przeglądarce, polubienia anonimowo (skrót identyfikatora przeglądarki), alerty przez anonimowy token. Nic osobowego nie trzymamy (RODO).
- **Operator PCI: tak, jako token.** Decyzje na kartach, uruchamianie pobrań i dotrenowanie Basala wymagają `RADAR_OPERATOR_TOKEN` (nagłówek `X-Operator-Token`; UI pyta raz). Bez ustawionego tokenu wszystko jest otwarte, co wystarcza do lokalnego demo.
- **Partnerzy (fundusze, urzędy): klucze API** (`RADAR_PARTNER_KEYS`, limit 60 zapytań/min).
- **Po hackathonie:** logowanie przez login.gov.pl / SSO instytucji dla zespołów PCI, synchronizacja portfela między urządzeniami.

## 5. Obrazki i grupowanie nowych rekordów na produkcji

- **Obrazek nie jest losowy.** Basal przypisuje sektor (12 sektorów) w ~1 ms; karta, rolka i kafel biorą ilustrację tego sektora (`static/sectors/<sektor>.webp`, wersja szeroka `sectors/wide/`). Nowy rekord ma więc obrazek od razu, bez generowania i bez kosztu. Zgłoszenie bez rozpoznanego sektora dostaje neutralną ilustrację.
- **Grupowanie bez zewnętrznych narzędzi:**
  - *Tematy*: technologia × branża z etykiet Basala (deterministyczne; nowy rekord trafia do grupy w chwili klasyfikacji).
  - *Rynki*: typ odbiorcy z modelu biznesowego (gminy, szpitale, szkoły…).
  - *Podobne metody*: k-means++ (cosinus) na embeddingach zapisanych przez Basala, przeliczany w API co 10 min (pamięć podręczna); nazwy grup z c-TF-IDF słów z tytułów.
  - *Podobne i duplikaty*: najbliżsi sąsiedzi po embeddingach (graf, „Podobne” w karcie, „Dublowanie prac”).
- Wszystko działa na CPU, w Postgresie i w procesie API, bez usług zewnętrznych.
