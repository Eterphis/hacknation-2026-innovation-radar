# Źródła danych według typów, jedno wejście do kolejki i przepływ pomysłu

- **Autor:** coordinator, 2026-11-21
- **Wejście:** `reports/data-access.md` (sprawdzone wywołania), `reports/pipeline-design.md`, kod `app/radar/sources/*` (budowany równolegle przez drugiego agenta), D-002, D-003, D-005, D-007, D-008
- **Status:** przyjęte (D-009, D-010): feed rolek po golden path; Basal bez LLM; platforma publiczna, głosują wszyscy; filmiki AI jako boost.
- **Zasada nadrzędna:** nowe źródło = wpis w `sources.yaml`, bez zmiany kodu, o ile jego transport już istnieje. Nowy transport = jedna klasa. Wszystko, co dalej, czyta tylko wspólny format `Signal`, nigdy surowy format źródła.

---

## 1. Inwentarz: co mamy zebrane

| # | Źródło | Stan (z prawdziwych wywołań) | Transport | Rola | Rodzaj rekordu |
|---|---|---|---|---|---|
| 1 | Biblioteka Nauki | **działa**, bez klucza; `oai_dc`, `oai_openaire`, `jats`; DOI ~50%, ORCID 0% | OAI-PMH | pomysł | publikacja |
| 2 | dLibra / czasopisma.pan.pl | prawdopodobnie działa, endpoint niepotwierdzony | OAI-PMH | pomysł | publikacja |
| 3 | RAD-on projekty | **działa**, bez klucza; ~49 tys., NCN + NCBR, filtr tylko po tytule | REST (token) | pomysł | projekt |
| 4 | RAD-on instytucje | **działa**; REGON, NIP, KRS, typ, województwo | REST | rejestr | organizacja |
| 5 | EPO Linked Data | **działa**, bez klucza; zgłaszający, CPC, rodzina | SPARQL | pomysł + dowód | patent |
| 6 | EPO dokument XML | **działa**; abstrakt, opis, zastrzeżenia | pobranie dokumentu po ID | dowód (wzbogacenie) | patent (pełny tekst) |
| 7 | Kohesio projekty | **działa** (lista); szczegóły 404 | REST | pomysł + ślad wdrożenia | projekt |
| 8 | Kohesio beneficjenci | **działa**; Wikidata, bez NIP | REST | rejestr + odbiorcy | organizacja |
| 9 | Kohesio CSV kraju | plik istnieje, URL nieustalony | snapshot (CSV) | pomysł | projekt |
| 10 | OpenAIRE Graph | **działa**; publikacje, projekty EC, organizacje z ROR/Wikidata; brak NCN/NCBR | REST | pomysł + rejestr + relacje | publikacja, projekt, organizacja |
| 11 | ROR dump | plik CC0 | snapshot (bulk) | rejestr | organizacja |
| 12 | TERYT, NUTS↔TERYT | pliki GUS | snapshot (bulk) | rejestr | jednostka terytorialna |
| 13 | GUS BDL | otwarte API, niesprawdzone | REST | kontekst odbiorcy | cechy gminy |
| 14 | GUS BIR (REGON) | klucz zakłada człowiek | SOAP/REST z kluczem | rejestr | organizacja |
| 15 | KRS | przerwa techniczna w chwili sprawdzenia | REST | dowód (spin-off) | organizacja |
| 16 | RSPO | brak połączenia | REST | rejestr (szkoły) | organizacja |
| 17 | EPO OPS | 403 bez klucza; konto zakłada człowiek | REST z kluczem | pomysł | patent |
| 18 | UPRP | **zablokowane** (Incapsula, 401) | ręczny eksport | pomysł | patent PL |
| 19 | PBN | klucz OPI, nierealne w 24 h | REST z kluczem | pomysł | publikacja |
| 20 | Interreg / keep.eu | eksport CSV ze strony | snapshot (CSV/XLSX) | pomysł | projekt |
| 21 | NCBR „sukcesy beneficjentów” | strona HTML | scraping HTML | pomysł + ślad wdrożenia | sukces wdrożeniowy |
| 22 | PPM, BazTOL | tylko interfejs WWW | scraping HTML / pominąć | pomysł | publikacja |
| 23 | Zgłoszenie człowieka (formularz, I-012 „opisz potrzebę”) | do zbudowania | push (HTTP) | pomysł albo **potrzeba** | rozwiązanie / potrzeba |

## 2. Podział na typy

Każde źródło opisują **trzy niezależne osie**. Dzięki temu nowe źródło klasyfikujemy, a nie programujemy.

### Oś A: transport (jak pobieramy), decyduje o klasie konektora

| Typ transportu | Klasa w kodzie | Źródła | Co trzeba dla nowego źródła tego typu |
|---|---|---|---|
| `oai-pmh` | `OaiPmhConnector` ✔ | 1, 2 | tylko `base_url`, `metadata_prefix` w YAML |
| `rest` | `RestConnector` ✔ | 3, 4, 7, 8, 10, 13, 15, 16, (17, 19 z kluczem) | URL, paginacja, `record_path`, `mapping` w YAML |
| `sparql` | `SparqlConnector` ✔ | 5 (+ Wikidata) | zapytanie z `{limit}`/`{offset}` |
| `graphql` | `GraphQLConnector` ✔ | (rezerwa) | zapytanie + ścieżki kursora |
| `snapshot` (CSV/JSON/JSONL) | `SnapshotConnector` ✔ | 9, 11, 12, 18, 20 | plik + `mapping` |
| `document` (pobierz pełny tekst po ID) | **brak**, do dodania | 6 | szablon URL, np. `.../publication/EP/{nr}/{kind}.xml` |
| `html` (scraping listy) | **brak**, do dodania | 21, 22 | selektory CSS w YAML, limit stron, poszanowanie robots |
| `push` (webhook, formularz, AMQP, Pub/Sub, Kafka) | `PushAdapter` ✔ | 23 | `mode: push` + `mapping` |

Brakują dwa transporty: `document` (wzbogacanie po ID, wywoływane z potoku, nie z harmonogramu) i `html`. Reszta nowych źródeł to sam YAML.

### Oś B: rola (po co nam rekord), decyduje o trasie w kolejce

| Rola | Znaczenie | Trasa |
|---|---|---|
| `idea` | kandydat na innowację: publikacja, patent, projekt, zgłoszenie | pełny potok: `normalize → resolve_org → dedup → gate → …` |
| `evidence` | dowód do istniejącego pomysłu: pełny tekst patentu, spin-off w KRS, ślad wdrożenia | `normalize → link`, nie tworzy nowego zadania, podnosi dojrzałość |
| `reference` | rejestry: organizacje, TERYT, NUTS | `load_reference`, poza kolejką pomysłów; zasila `resolve_org` |
| `demand` | potrzeba odbiorcy: zgłoszona przez urzędnika/gminę, katalog beneficjentów, cechy gmin | indeks odbiorców; dopasowanie pomysł ↔ potrzeba |

Jedno źródło może mieć kilka ról (Kohesio: `idea` dla projektów, `demand` + `reference` dla beneficjentów). W YAML to dwa wpisy z tym samym transportem.

### Oś C: rodzaj rekordu (co to jest), decyduje o mapowaniu i regułach dojrzałości

`publication | patent | project | solution | need | organization | territory | success_story`

Reguły dojrzałości z `pipeline-design.md` §8 zależą tylko od rodzaju, nie od źródła: patent z dowolnego źródła daje `tech_ready`, projekt wdrożeniowy z dowolnego źródła daje `business_ready`.

### Oś D (pomocnicza): dostępność, decyduje o trybie demo

`live` (1, 3, 4, 5, 6, 7, 8, 10) · `key_by_human` (14, 17, 19) · `snapshot_only` (9, 11, 12, 18, 20) · `blocked_or_down` (15, 16, 18 automatycznie) · `scrape` (21, 22).
Tryb demo uruchamia tylko wpisy z `demo: true` (snapshot), jak w `config.py`.

## 3. Jedno wejście do kolejki: `Signal` v1

Każdy konektor i każdy push kończy się `Envelope` (już jest w `sources/base.py`). Etap `normalize` zamienia go na **`Signal`**: jedyny format, który czytają dalsze etapy i agenci. Mapowanie źródło → `Signal` żyje w `sources.yaml` (`mapping`), więc dalsze etapy nie wiedzą, skąd rekord przyszedł.

```jsonc
{
  "schema": "radar.signal/v1",
  "signal_id": "sig_01JD…",               // ULID, nadawany przy normalize
  "source": {
    "id": "biblioteka-nauki",             // klucz w sources.yaml
    "transport": "oai-pmh",               // oś A
    "role": "idea",                       // oś B
    "kind": "publication",                // oś C
    "external_id": "oai:bibliotekanauki.pl:5104",
    "url": "https://bibliotekanauki.pl/articles/5104",
    "received_via": "pull",               // pull | webhook | pubsub | upload
    "fetched_at": "2026-11-21T14:02:11Z"
  },
  "content_hash": "sha256:…",             // idempotencja (raw_id, stage, content_hash)
  "raw_ref": "raw_records/8812",          // surowy rekord zostaje w bazie, nie w wiadomości

  "core": {                               // wspólne pola, każde może być null
    "title": {"pl": "…", "en": "…"},
    "text":  {"pl": "…", "en": "…"},      // abstrakt / opis / treść zgłoszenia
    "language": "pl",
    "date": "2024-05-12",
    "ids": {"doi": "10.…", "patent_app": null, "project_code": null, "ror": null, "wikidata": null, "regon": null},
    "actors": [                           // ludzie i organizacje z rolą, przed rozpoznaniem
      {"name": "Politechnika Rzeszowska", "role": "affiliation", "org_hint": "Wydział Budowy Maszyn…"},
      {"name": "J. Kowalski", "role": "author"}
    ],
    "topics": ["kompozyty", "badania nieniszczące"],
    "classes": {"cpc": [], "fos": ["02"]},
    "money": {"total": null, "eu": null, "currency": "PLN", "reliable": false},
    "place": {"teryt": null, "nuts": null, "voivodeship": null}
  },

  "rights": {"licence": "CC BY 4.0", "llm_may_read_fulltext": true},
  "attachments": [                        // multimodalność: PDF, obraz, wideo, nagranie zgłoszenia
    {"type": "application/pdf", "ref": "blob://…", "llm_may_read": false}
  ],
  "extra": {},                            // pola specyficzne dla źródła, bez gwarancji
  "trace": [{"stage": "normalize", "at": "…", "by": "mapping:biblioteka-nauki@3"}]
}
```

**Dlaczego tak:**
- `core` jest celowo płaski i wielojęzyczny, bo LLM i reguły potrzebują tego samego niezależnie od źródła.
- `actors` zamiast osobnych `authors`/`affiliations`/`applicants`: patent, projekt i publikacja mają różne role, ale jeden mechanizm `resolve_org`.
- `attachments` z `llm_may_read`: wejście dla agenta-analityka (§7), z poszanowaniem praw (Biblioteka Nauki: 12/20 „wszystkie prawa zastrzeżone”).
- `extra` jest jawnie „bez gwarancji”: nikt dalej nie może na nim polegać, więc źródło może zmienić format bez psucia potoku.
- Wersja mapowania w `trace` (`@3`) pozwala przeliczyć rekordy po poprawie mapowania.

**Zgodność z istniejącym kodem:** `Record` w `models.py` ma już większość pól `core`. Wystarczy dodać `role`, `actors`, `attachments`, `rights` (albo trzymać `Signal` jako JSON obok `Record`). Szczegół do ustalenia z agentem budującym aplikację, bez przepisywania konektorów.

### Elastyczność dla nieznanych źródeł

1. **Znany transport, nowy format:** dopisujemy wpis w YAML. Polecenie `radar source draft <url>` pobiera 3 próbki, LLM **proponuje** `record_path` i `mapping`, człowiek zatwierdza, mapowanie trafia do YAML z wersją. LLM nie mapuje każdego rekordu, tylko raz pisze konfigurację.
2. **Test kontraktu na źródło:** zapisane próbki + oczekiwany `Signal`; CI łapie zmianę formatu źródła.
3. **Bramka jakości mapowania:** jeżeli > 20% rekordów z partii nie ma `title` lub `text`, źródło przechodzi w `degraded`, a rekordy do `needs_review`, zamiast cicho iść dalej (D-005).

## 4. Topologia kolejek (RabbitMQ + Celery, D-003)

```
[konektory pull]──┐
[push/formularz]──┼─► harvest ─► normalize ─► resolve_org ─► dedup ─► gate ─► task.create
[snapshot]────────┘                  │                                 │
                                     ├─ role=evidence ─► link          ├─ hold ─► needs_review (operator)
                                     ├─ role=reference ─► registry     └─ reject ─► archived (z powodem)
                                     └─ role=demand ─► demand_index

task.create ─► analyze ─► review(„co przemawia przeciw”) ─► brief ─► proposal ─► operator(zatwierdź/odrzuć)
                                                                                    │
                                              feed.publish ◄────────────────────────┘
                                                   │
                         feedback.events ─► ranking ─► top-N ─► genai.render ─► feed.publish (wersja wzbogacona)
                                                   └──────────────► ponowna ocena (analyze, z nowymi danymi)
```

- Exchange `radar.signals` typu `topic`, klucz routingu `<role>.<kind>.<source_id>`, np. `idea.patent.epo-ld`. Nowe źródło nie wymaga nowej kolejki: trafia na istniejący klucz.
- Każdy etap: `acks_late`, idempotencja po `(signal_id, stage, content_hash)`, retry z backoff, DLQ, liczniki (przyjęte = gotowe + przegląd + odrzucone + w toku + DLQ).
- Etapy z LLM mają osobne kolejki i limit współbieżności, żeby koszt był przewidywalny.

## 5. Filtr na wejściu: Basal (`gate`), bez LLM

**Cel (człowiek, D-010):** odsiać nieodpowiednie zgłoszenia i posortować resztę według typów z treści zadania **zanim** cokolwiek trafi do LLM. Zadań w kolejce może być dużo, a czas i koszt LLM są wąskim gardłem, więc LLM dostaje tylko to, co przeszło Basal, w kolejności priorytetu.

Basal działa w kodzie: reguły, słowniki, wynik `resolve_org` i ewentualnie mały lokalny klasyfikator (embeddingi wielojęzyczne + regresja logistyczna albo fastText). Żadnego wywołania LLM, milisekundy na rekord, działa offline (też w trybie demo).

### 5.1 Odsiew nieodpowiednich (`reject` z powodem, nic nie ginie, D-005)

| Powód | Jak wykrywamy |
|---|---|
| spam, reklama, treść bez związku z innowacją | słownik fraz + linki zewnętrzne + klasyfikator „na temat / nie na temat” |
| treść obraźliwa lub wulgarna | słownik PL/EN + klasyfikator toksyczności (lokalny) |
| za mało informacji | brak tytułu lub opisu, opis < ~200 znaków (`pipeline-design.md` §3) |
| poza zakresem zadania | organizacja rozpoznana jako prywatna firma bez instytucji publicznej w `actors` (treść §2: szkoły, uczelnie, JST, inne instytucje publiczne) |
| duplikat | wynik `dedup` (D-007), zadanie idzie do klastra, nie tworzy nowego |
| dane osobowe w treści zgłoszenia | wzorce PESEL, telefon, e-mail → zamaskowane albo `hold` (RODO) |

Zgłoszenia od ludzi (formularz, komentarze z feedu) przechodzą ten sam odsiew.

### 5.2 Sortowanie według typów z treści zadania

Każdy sygnał dostaje dwie etykiety i pewność:

- **Typ instytucji** (treść §2): `szkoła | uczelnia | instytut | JST | inna_publiczna | unknown`. Źródło: rejestr z `resolve_org` (RAD-on, RSPO, TERYT), nie zgadywanie.
- **Typ innowacji** (treść §2, także nietechnologiczne): `technologiczna | organizacyjna | edukacyjna | społeczna | procesowa | usługowa | unknown` (lista wspólna z `extract.py`). Źródło: rodzaj rekordu (patent → technologiczna), klasy CPC/FOS, słowniki sygnałowe, klasyfikator.
- **Dojrzałość wstępna** z reguł `pipeline-design.md` §8.

### 5.3 Routing i priorytet w kolejce

- Wynik Basal to klucz routingu `task.<typ_instytucji>.<typ_innowacji>` na exchange `radar.tasks` (RabbitMQ, D-003; Redis najwyżej jako backend wyników Celery i cache, nie jako broker).
- Kolejki LLM z `x-max-priority`; priorytet = pewność Basal + kompletność dowodów + luka „ukryta innowacja” (`tech_ready` bez wdrożenia) + świeżość.
- Limit współbieżności workerów LLM w konfiguracji; reszta czeka w kolejce, nic nie przepada.
- `unknown` na którejś osi → niski priorytet albo `hold` do operatora, zamiast przepalać LLM na niejasnych rekordach.
- Dzięki typom feed i operator mogą filtrować („pokaż innowacje edukacyjne ze szkół”), a ranking porównuje pomysły w obrębie typu.

**Wynik Basal** zapisany przy sygnale:
```json
{"decision": "pass", "reject_reason": null,
 "institution_type": {"value": "JST", "confidence": 0.95, "by": "registry:teryt"},
 "innovation_type": {"value": "organizacyjna", "confidence": 0.72, "by": "keywords+clf@1"},
 "maturity_hint": "business_ready", "priority": 0.81}
```

**Kalibracja:** progi i słowniki stroimy na zbiorze testowym (D-008 pkt 8); etykiety „to już istnieje” i zgłoszenia moderacji z feedu (§9) go powiększają. Na demo: 1–3 tys. sygnałów → ~100–300 zadań do LLM.

## 6. Zadanie w kolejce: `IdeaTask` v1

`gate` z wynikiem `pass` tworzy jedno zadanie na **klaster** (nie na rekord), z dowodami ze wszystkich źródeł klastra.

```jsonc
{
  "schema": "radar.task/v1",
  "task_id": "tsk_…",
  "cluster_id": 412,
  "signals": ["sig_…", "sig_…"],          // publikacja + patent + projekt tej samej innowacji
  "org": {"org_id": "org:prz", "type": "uczelnia publiczna", "region": "PL823", "confidence": 0.95},
  "gate": {"decision": "pass", "institution_type": "uczelnia", "innovation_type": "technologiczna", "by": "basal@1"},
  "maturity_hint": "tech_ready",
  "priority": 0.74,                        // z gate + świeżość + luka „ukryta innowacja”
  "budget": {"max_tool_calls": 8, "max_llm_retries": 2},
  "status": "queued"                       // queued → analyzing → reviewed → briefed → proposed → approved|rejected → published
}
```

## 7. Agent-analityk: ocena wykonalności i potencjału (`analyze`)

Rozszerza I-011. Dostaje `IdeaTask`, narzędzia z `ideation-3.md` (`get_record`, `lookup_registry`, `find_similar`, `find_duplicates`, `list_recipients`) oraz `search_sources`. Każde twierdzenie z cytatem lub linkiem do rekordu; kod sprawdza cytaty.

| Sekcja | Co agent ustala | Skąd dowody |
|---|---|---|
| **Pomysł** | co to jest, jaki problem, co nowego | tekst sygnałów |
| **Innowacyjność** | nowość względem podobnych (`find_similar`), stan ochrony | dedup warstwa 5, EPO |
| **Klient i odbiorca** | kto ma problem, ile takich podmiotów, kto już płaci za podobne | `demand_index`, Kohesio beneficjenci, GUS BDL |
| **Pomysł biznesowy** | ścieżka: licencja / spin-off / pilotaż w JST / transfer do innej instytucji / grant; model przychodu lub finansowania | reguły ścieżek + projekty Kohesio/NCBR |
| **SDLC / wykonalność** | co trzeba zbudować, by wdrożyć (TRL → MVP → pilotaż → skala), szacunek etapów, zależności, kompetencje, dane | dojrzałość z dowodów, opis rozwiązania |
| **Ryzyka** | techniczne, prawne (IP, RODO, zamówienia publiczne), rynkowe, organizacyjne, finansowe | brak dowodów = ryzyko jawnie nazwane |
| **Mitygacje** | jedna konkretna akcja na ryzyko, z właścicielem (twórca / PCI / odbiorca) | — |
| **Ocena** | 0–5 na kryterium z jawnym uzasadnieniem: dojrzałość, przenaszalność, skala problemu, koszt wdrożenia, siła dowodów, innowacyjność | wszystko powyżej |

Potem **jedno przejście recenzenta** (I-014): szuka słabych punktów i pisze „Co przemawia przeciw”. Bez zmian względem D-008, tylko więcej sekcji.

Wyjście: `Assessment` (JSON) zapisany przy karcie; schemat walidowany, brak cytatu → `needs_review`.

## 8. Brief i propozycja

- **Brief** (`brief`, LLM, krótki): jedna strona dla urzędnika w układzie „uzasadnienia” z `ideation-3.md` (ustalenia → kryteria → ocena → przeciw → rozstrzygnięcie → ograniczenia). Wejście: `Assessment`. Zero nowych faktów.
- **Propozycja** (`proposal`): konkretna oferta dla 1–3 odbiorców z `list_recipients`: co proponujemy, dlaczego im, pierwszy krok, mierniki (np. liczba pilotaży w 12 mies.), szacunek kosztu i czasu z sekcji SDLC. Jedna propozycja na parę pomysł ↔ odbiorca.
- **Operator PCI zatwierdza lub odrzuca** (D-008). Tylko zatwierdzone idą do feedu. Bez wysyłki do odbiorców (D-008 pkt 5).

## 9. Otwarta platforma z rolkami: ocenia ją publiczność (`feed`)

**Zasada (człowiek, D-010):** platforma jest publiczna i dostępna dla każdego. O tym, które pomysły idą wyżej, decydują głosy ludzi, a nie tylko operator. Operator PCI zatwierdza tylko to, co trafia do feedu (D-008); kolejność w feedzie ustalają użytkownicy.

- **Oglądanie:** bez konta.
- **Głosowanie:** lekkie konto (e-mail z linkiem albo logowanie zewnętrzne), żeby jedna osoba miała jeden głos na pomysł. **Każdy głos waży tyle samo**, bez dodatkowej wagi dla kont instytucjonalnych.
- **Odznaka „instytucja”** (JST, uczelnia, szkoła) jest tylko informacją przy sygnałach intencji („Gmina X chce to wdrożyć”), nie mnożnikiem głosu.
- **Komentarze** przechodzą odsiew Basal (§5.1) i można je zgłosić do moderacji.

**Format rolki** (generowany z briefu, deterministycznie, bez nowych faktów):
1. Hak: problem w jednym zdaniu („Gminy tracą X na …”).
2. Rozwiązanie: co i kto to zrobił (instytucja, region).
3. Dowód: odznaka dojrzałości z linkiem (patent, projekt, wdrożenie).
4. Dla kogo: typ odbiorcy.
5. Wezwanie: 👍 / „wdrożyłbym u siebie” / „szukam partnera” / „to już istnieje”.

Pionowe karty z przewijaniem, tekst + grafika (na start bez wideo). Pełny brief po dotknięciu.

**Zdarzenia** (kolejka `feedback.events`, append-only):
`view`, `dwell_ms`, `expand`, `like`, `vote{criterion, 1–5}`, `would_adopt{org_type}`, `seeking_partner`, `already_exists{link}`, `comment`, `share`.

**Ranking:**
- Wynik = dolna granica Wilsona dla polubień + ważone sygnały intencji (`would_adopt` ×5, `seeking_partner` ×3) + średnia bayesowska głosów; zanik w czasie.
- Jedna osoba = jeden głos na pomysł, równa waga (zasada wyżej); sygnały intencji liczone raz na osobę.
- Ochrona przed nabijaniem: weryfikacja konta, limit zdarzeń na minutę, odrzucanie podejrzanych serii (wiele kont z jednego adresu w krótkim czasie). Ranking pokazuje liczbę głosów jawnie.
- `already_exists` z linkiem wraca do `dedup` warstwy 5 i do recenzenta: feedback poprawia ocenę, nie tylko popularność.

**Pętla zwrotna:** co tydzień sygnały z feedu trafiają do `analyze` jako nowe dowody (popyt), a etykiety `already_exists` / `would_adopt` budują zbiór testowy dla `gate` (dziś go nie ma, D-008 pkt 8).

## 10. Filmiki AI jako boost dla najlepszych (`genai.render`)

**Cel (człowiek, D-010):** film nie ocenia ani nie dowodzi niczego, tylko **promuje** pomysł, który ludzie już wybrali. Pomysł z filmem dostaje wyższe miejsce w feedzie i lepiej się udostępnia.

- Kto dostaje boost: top-N z rankingu głosów (np. 10 tygodniowo, albo po przekroczeniu progu głosów), w obrębie typu z §5.2, żeby szkoły nie przegrywały z uczelniami.
- Co generujemy: krótki pionowy film (15–30 s) pod format rolki: hak → problem → rozwiązanie → kto to zrobił → wezwanie. Tańsze warianty: grafika koncepcyjna, animowana karta.
- Wejście **wyłącznie** z zatwierdzonego briefu; na materiale znak „wizualizacja AI, nie zdjęcie rzeczywistego wdrożenia”.
- Budżet na tydzień w konfiguracji; zadanie z kosztem w `provenance`. Publikacja po zatwierdzeniu operatora.

## 11. Kolejność budowy (propozycja)

| Krok | Zakres | Kiedy |
|---|---|---|
| 1 | `Signal` v1 + `role` w YAML + test kontraktu na 4 źródła golden path (RAD-on, BN, EPO, Kohesio) | teraz, razem z agentem budującym aplikację |
| 2 | Basal: odsiew + typy instytucji i innowacji + routing z priorytetem; `IdeaTask` | golden path 18:00 |
| 3 | `analyze` + recenzent + brief (I-011, D-008) | golden path |
| 4 | konektor `document` (EPO XML), lokalny klasyfikator typów do Basal | wieczór |
| 5 | propozycja + feed rolek + polubienia/głosy | noc, zaraz po golden path (D-009) |
| 6 | ranking + genai dla top-N | jeśli czas; na pitch wystarczy 1 wygenerowany przykład |
| 7 | konektor `html` (NCBR sukcesy), `radar source draft` | po hackathonie (C5: rozwój) |

## 12. Pytania do człowieka

1. ~~Czy feed rolek wchodzi do zakresu przed oddaniem?~~ **Odpowiedź (D-009):** tak, po golden path; genai dla top-N tylko jeśli starczy czasu.
2. ~~Kto głosuje?~~ **Odpowiedź (D-010):** każdy; platforma publiczna, jeden głos na osobę, równa waga.
3. ~~Czym jest Basal?~~ **Odpowiedź (D-010):** filtr bez LLM: odsiew nieodpowiednich zgłoszeń i sortowanie według typów z treści zadania, żeby nie marnować LLM przy dużej liczbie zadań w kolejce. Filmiki AI służą do boostowania pomysłów wybranych przez ludzi.
