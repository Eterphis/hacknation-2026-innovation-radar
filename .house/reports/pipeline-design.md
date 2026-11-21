# Od surowych danych do karty innowacji: projekt potoku

- **Autor:** coordinator, 2026-11-21
- **Wejście:** notatka `zrodla-danych.md` (Biblioteka Nauki, OpenAIRE, Kohesio), `reports/data-access.md`, architektura D-003
- **Wyjście:** karta innowacji w strukturze rekordu (warstwy `raw` → `normalized` → `enriched`), gotowa do oceny i kierowania
- **Status:** propozycja. Punkty oznaczone **[sprawdzić]** wymagają jednego prawdziwego zapytania, zanim trafią do zadania.

## 0. Zasada

Kod robi wszystko, co da się zrobić deterministycznie: parsowanie, ujednolicanie, dopasowanie do rejestrów, łączenie po identyfikatorach, poziom dojrzałości.
LLM dostaje tylko to, czego kod nie umie: wyciągnięcie z opisu, **jakie rozwiązanie** powstało, **jaki problem** rozwiązuje i **dla kogo**, oraz wybór z gotowej listy, gdy dopasowanie jest niepewne.
Każda odpowiedź LLM ma cytat ze źródła, a cytat jest sprawdzany w kodzie.

## 1. Dane referencyjne (ładowane raz, odświeżane co tydzień)

Przed pobieraniem rekordów budujemy **rejestr organizacji**: jedną tabelę z identyfikatorami, typem, regionem i wszystkimi wariantami nazw.

| Rejestr | Co daje | Dostęp |
|---|---|---|
| ROR (dump) | uczelnie i instytuty, aliasy nazw, skróty, identyfikatory zewnętrzne (Wikidata, ISNI), miasto | plik do pobrania, CC0 |
| POL-on / RAD-on | uczelnie i instytuty w PL, publiczna czy niepubliczna, adres; możliwe też projekty i patenty uczelni | publiczne dane **[sprawdzić API i zakres]** |
| RSPO | szkoły i placówki: REGON, typ, publiczna/niepubliczna, adres, kod TERYT | publiczne API **[sprawdzić]** |
| TERYT (GUS) | gminy, powiaty, województwa, kody | pliki do pobrania |
| GUS BIR (REGON) | typ podmiotu, forma prawna, PKD, adres, po NIP/REGON | darmowy klucz po rejestracji (konto zakłada człowiek) |
| KRS (API MS) | spółki, w tym spin-offy uczelni, wspólnicy | otwarte API **[sprawdzić]** |
| GUS BDL | cechy gmin: ludność, budżet, wskaźniki (do dopasowania odbiorców) | otwarte API |
| NUTS ↔ TERYT | przejście z regionu Kohesio na nasze kody | tabela przejścia |

Wynik: tabela `organizations` (`org_id`, `ids{ror,regon,nip,rspo,teryt,krs}`, `type`, `is_public`, `region`, `aliases[]`).
Reguły `is_public`: uczelnia publiczna wg POL-on, instytut badawczy lub PAN, szkoła publiczna wg RSPO, JST wg TERYT; reszta `unknown`, nigdy zgadywana.

## 2. Pobieranie (`harvest`)

Jeden konektor na źródło. Każdy zapisuje surową odpowiedź (`raw`) z `content_hash`, zanim cokolwiek przetworzy.

**Biblioteka Nauki (OAI-PMH)**
- `ListRecords` z `from=<ostatni datestamp>`, stronicowanie przez `resumptionToken`; rekordy z nagłówkiem `status="deleted"` oznaczamy `deleted`.
- Format metadanych: `oai_dc` na start, bogatszy format, jeśli serwer go oferuje **[sprawdzić `ListMetadataFormats`, czy jest ORCID i DOI]**.

**OpenAIRE Graph (REST)**
- Publikacje i projekty z filtrem kraju organizacji = PL (a dla demo: organizacje z Podkarpacia z rejestru), z darmowym tokenem (7200 zapytań/h).
- Pobieramy też relacje publikacja ↔ projekt ↔ organizacja, bo to gotowe połączenia o wysokiej pewności.
- Brak daty zmiany w notatce, więc zmiany wykrywa `content_hash`.

**Kohesio**
- Snapshot: eksport CSV/XLSX dla Polski (stabilny), uzupełniony o szczegóły projektu, gdy potrzebni są beneficjenci.
- Endpoint JSON strony jest nieudokumentowany, więc tylko jako pomoc, nie jako jedyne źródło.

**Zakres na demo:** ostatnie 5 lat, organizacje z województwa podkarpackiego plus 2–3 tematy z inteligentnych specjalizacji regionu (lotnictwo, motoryzacja, jakość życia, ICT). Szacunek: 1–3 tys. rekordów, z czego do LLM po filtrach trafia 100–300.

## 3. Parsowanie i ujednolicenie (`normalize`, bez LLM)

- Mapowanie pól źródła na strukturę rekordu (osobna mapa na źródło).
- Tekst: usunięcie HTML, ujednolicenie spacji, wykrycie języka, rozdzielenie PL/EN.
- Liczby: polski przecinek dziesiętny (`"336000000,00"` → `336000000.00`), tablice jednoelementowe rozpakowane, waluta.
- Daty do ISO 8601; status projektu z dat względem dzisiaj (`planned | running | finished`).
- Kwoty równe 0 w OpenAIRE → `amounts_reliable: false`.
- Prawa: `fulltext_licence` i `llm_may_read_fulltext` z pola praw (Biblioteka Nauki), licencji źródła (OpenAIRE CC-BY) albo `unknown`.
- **Bramka jakości:** brak tytułu lub opisu albo opis krótszy niż ~200 znaków → `needs_review`, rekord nie idzie dalej do LLM.

## 4. Rozpoznanie organizacji (`resolve_org`), najważniejszy krok

Od niego zależy filtr „instytucja publiczna”, region, łączenie źródeł i odbiorcy.

1. **Rozbicie afiliacji:** jeden tekst może zawierać kilka jednostek i hierarchię („Katedra X, Wydział Y, Politechnika Rzeszowska, Rzeszów”). Dzielimy po separatorach i zostawiamy poziom instytucji.
2. **Ujednolicenie nazwy:** małe litery, bez polskich znaków, bez form prawnych (sp. z o.o., S.A.), rozwinięcie skrótów (PRz, UR, im.), bez wydziałów i katedr.
3. **Dopasowanie kaskadowe**, od najpewniejszego:
   - identyfikator ze źródła (ROR, NIP, REGON), pewność 1.0;
   - słownik aliasów z rejestrów (ROR, POL-on, RSPO) i ręczny, pewność 0.95;
   - dopasowanie rozmyte nazwy plus zgodność miasta, pewność według podobieństwa;
   - podobieństwo embeddingów do nazw z rejestru;
   - **LLM jako ostatnia deska:** dostaje 5 kandydatów z rejestru i wybiera jednego albo „żaden”; nie może wymyślić organizacji spoza listy.
4. **Progi:** ≥ 0.90 przyjęte; 0.70–0.90 przyjęte z flagą do przeglądu; < 0.70 → `unknown` i `needs_review`.
5. **Wzbogacenie z rejestru:** `type`, `is_public`, `teryt`, `woj`, `powiat`, `nuts3`, współrzędne.
6. Każde nowe dopasowanie trafia do słownika aliasów, więc następny rekord z tą samą nazwą przechodzi bez LLM.

## 5. Ludzie i finansowanie

- Osoby: ORCID, gdy jest (OpenAIRE); poza tym imię i nazwisko ujednolicone i powiązane z `org_id` w obrębie rekordu. Bez e-maili i innych danych kontaktowych (RODO); kontakt kierujemy do instytucji.
- Finansowanie: grantodawca, program, nabór, kwoty i status z OpenAIRE i Kohesio; udział UE liczony z `euBudgets / totalBudgets`.

## 6. Łączenie źródeł i duplikaty (`link`)

Od najpewniejszych połączeń:

| Połączenie | Metoda | Pewność |
|---|---|---|
| publikacja ↔ projekt | relacje z OpenAIRE | wysoka |
| ta sama publikacja w Bibliotece Nauki i OpenAIRE | DOI, gdy jest; inaczej tytuł (rozmyty) + rok + nazwisko autora | wysoka / średnia |
| badanie ↔ inwestycja w Kohesio | ten sam `org_id` jako afiliacja i beneficjent + podobieństwo opisu (embeddingi) + kolejność w czasie (publikacja przed startem projektu) | średnia, zawsze z wartością pewności |
| wynik ↔ patent (później, UPRP/EPO) | zgłaszający = `org_id`, twórcy = autorzy, podobieństwo opisu | średnia |

- Duplikaty łączymy w `cluster` z jednym rekordem kanonicznym; dalsze kroki działają na klastrze, nie na pojedynczych wpisach.
- Połączenie poniżej progu pewności zostaje zapisane jako „możliwe”, ale nie podnosi dojrzałości.

## 7. Czy to w ogóle innowacja? (`prefilter` + `extract`)

Większość publikacji to nie są wdrażalne rozwiązania, więc najpierw tani filtr, potem LLM.

**Filtr regułowy (bez LLM):** organizacja publiczna albo `unknown`; typ rekordu; dziedziny stosowane (FOS 02 inżynieria, 03 medycyna, 05 nauki społeczne itd.); słowa sygnałowe w tytule lub abstrakcie („opracowano”, „wdrożenie”, „prototyp”, „metoda”, „system”, „program”, „model działania”, „pilotaż”).

**LLM, krok 1 (klasyfikacja):** „Czy ten opis przedstawia konkretne rozwiązanie, które ktoś inny mógłby zastosować?” Odpowiedź `tak | nie | niejasne` z cytatem. `nie` kończy przetwarzanie rekordu ze statusem `not_innovation` (zapisany, nie zgubiony).

**LLM, krok 2 (ekstrakcja):** dla `tak` model wypełnia pola `enriched`:
- `solution_name`, `problem_solved`, `what_is_new`, `target_users`, `innovation_type` (z listy), `requirements`, `summary_pl`;
- dla każdego pola: cytat ze źródła i pewność.

**Walidacja w kodzie:**
- schemat (wymagane pola, wartości z list);
- każdy cytat musi występować w tekście wejściowym (dopasowanie po ujednoliceniu spacji);
- typ innowacji z listy, nie wolny tekst.

Nie przechodzi → ponowienie z listą błędów (maks. 2 razy) → `needs_review`. Dostawca, model i wersja polecenia trafiają do `provenance`.

## 8. Dojrzałość z dowodów (`maturity`, reguły, bez LLM)

| Poziom | Wymagany dowód |
|---|---|
| `exploring` | publikacja albo projekt badawczy |
| `tech_ready` | patent albo prototyp lub pilotaż opisany w projekcie |
| `business_ready` | projekt wdrożeniowy lub inwestycyjny (Kohesio, NCBR sukces), spin-off w KRS |
| `market_ready` | wdrożenie w więcej niż jednej instytucji albo produkt w sprzedaży |

- `missing` = czego brakuje do następnego poziomu.
- `hidden = true`, gdy poziom to `tech_ready` albo wyższy, a nie ma śladu wdrożenia poza instytucją, w której powstało.
- Każdy poziom wskazuje `evidence_ids`, więc w interfejsie odznaka dojrzałości linkuje do rekordów.

## 9. Wyjście (`export`)

Dla każdego klastra jedna **karta innowacji** w strukturze rekordu, z flagą:

- `ready_for_scoring`: są pola wymagane, organizacja rozpoznana z pewnością ≥ 0.70, ekstrakcja przeszła walidację;
- `needs_review`: z listą powodów (np. „afiliacja nierozpoznana”, „brak cytatu dla problem_solved”);
- `not_innovation` lub `deleted`: zachowane, żeby liczniki się zgadzały.

Formaty: rekord w bazie + wiadomość do kolejki `score`; eksport JSONL (cały zbiór) i CSV (widok dla PCI).

## 10. Kolejki (D-003)

`load_reference` (raz na tydzień) → `harvest` → `normalize` → `resolve_org` → `link` → `prefilter` → `extract` → `maturity` → `export` → dalej `score` i `route`.
Każda kolejka z `acks_late`, idempotencją po `(source, record_id, stage, content_hash)`, retry i dead-letter. Liczniki na etap: przyjęte = gotowe + `needs_review` + `not_innovation` + w toku + DLQ.

## 11. Kontrola jakości

- **Zbiór testowy:** 40 rekordów oznaczonych ręcznie (organizacja, publiczna, innowacja tak/nie, typ). Mierzymy trafność rozpoznania organizacji, filtra innowacji i typu przy każdej zmianie polecenia lub dostawcy LLM.
- **Ekran operatora:** liczniki etapów, lista `needs_review` z powodami, przycisk „zatwierdź / popraw / odrzuć”; poprawki wracają do słownika aliasów.
- **Na pitch:** liczby z tego zbioru (np. „rozpoznanie organizacji 92% na 40 przypadkach”), a nie deklaracje.

## 12. Przykład

1. **Biblioteka Nauki:** artykuł z afiliacją „Wydział Budowy Maszyn i Lotnictwa, Politechnika Rzeszowska”, abstrakt PL o nowej metodzie kontroli kompozytów.
2. **resolve_org:** słownik aliasów → `org:prz` (ROR, REGON, uczelnia publiczna, podkarpackie, PL823), pewność 0.95.
3. **link:** OpenAIRE ma ten sam tytuł z ORCID autorów i relację do projektu badawczego; Kohesio ma inwestycję z beneficjentem `org:prz` o podobnym opisie, start dwa lata po publikacji (pewność 0.71, „możliwe”).
4. **extract:** `solution_name` = metoda kontroli kompozytów, `problem_solved` = wykrywanie wad bez niszczenia elementu, `target_users` = zakłady lotnicze i laboratoria, typ = technologiczna; każde pole z cytatem.
5. **maturity:** publikacja + projekt badawczy = `exploring`; połączenie z inwestycją poniżej progu, więc nie podnosi poziomu; `missing = [patent albo pilotaż]`.
6. **export:** `ready_for_scoring`, do kolejki `score`.

Przykład jest ilustracją zasady, nie prawdziwym rekordem.

## 13. Do sprawdzenia przed planem zadań

1. Biblioteka Nauki: `ListMetadataFormats`, czy pełny rekord ma ORCID i DOI.
2. OpenAIRE `/organizations`: typ, kraj, region, ROR.
3. Kohesio: czy szczegóły projektu lub eksport CSV mają NIP/REGON beneficjenta.
4. POL-on / RAD-on: publiczne API, czy obejmuje patenty i projekty uczelni.
5. RSPO i KRS: publiczne API bez klucza.
6. GUS BIR: założenie darmowego klucza (człowiek).

## 14. Wyniki sprawdzenia (2026-11-21 13:22)

Szczegóły i wywołania: `reports/data-access.md`, sekcja „Checked with real calls”.

1. **Biblioteka Nauki:** formaty `oai_dc`, `oai_openaire`, `jats`, `bwmeta`. **ORCID brak** (0 na 20 rekordów), **DOI w ok. połowie** (11 na 20), afiliacja jako tekst. 12 na 20 rekordów ma „wszystkie prawa zastrzeżone”, więc LLM pracuje na metadanych.
2. **OpenAIRE `/organizations`:** nazwy, aliasy, ROR, Wikidata, PIC; **brak typu i regionu**. Projektów **NCN i NCBR nie ma**.
3. **Kohesio:** `/api/beneficiaries` działa i daje **link do Wikidata** (wspólny klucz z OpenAIRE), **bez NIP/REGON**. Szczegóły projektu, Linked Data i SPARQL niedostępne (404/403). CSV kraju ma opcjonalny identyfikator beneficjenta, adres pliku nieustalony.
4. **RAD-on:** działa bez klucza. Instytucje mają **REGON, NIP, KRS, rodzaj (publiczna/niepubliczna) i województwo**. Projekty krajowe z instytucjami realizującymi i abstraktem PL (NCN widoczne w próbce, NCBR niesprawdzone). **Patentów brak.**
5. **RSPO:** API nie odpowiada pod sprawdzonym adresem. **KRS:** przerwa techniczna w chwili sprawdzenia.
6. **GUS BIR:** nie sprawdzane, wymaga klucza zakładanego przez człowieka.

Zmiany w projekcie: łączenie Biblioteki Nauki po DOI, a nie ORCID (krok 6); Wikidata jako klucz OpenAIRE ↔ Kohesio (krok 4); RAD-on jako główny rejestr uczelni i instytutów oraz źródło projektów krajowych, przynajmniej NCN (krok 1 i 2); patenty wciąż bez sprawdzonego źródła.

## 15. Patenty i NCBR (2026-11-21 13:27)

- **EPO Linked Data działa bez klucza:** wyszukiwanie zgłaszającego po nazwie, numer, rodzaj, daty zgłoszenia i udzielenia, klasy CPC, rodzina patentowa, twórcy; pełny XML dokumentu z abstraktem, opisem i zastrzeżeniami. Politechnika Rzeszowska: 17 publikacji EP. To źródło dowodu `tech_ready` w kroku 8.
- **UPRP (patenty krajowe PL):** wyszukiwarka zablokowana ochroną przed botami, API wymaga uwierzytelnienia (401). Bez automatycznego dostępu; zostaje ręczny eksport jako snapshot albo ograniczenie opisane w README.
- **RAD-on:** projekty NCBR są (oprócz NCN); 48 853 projekty, filtr po tytule działa, po instytucji i finansującym nie, więc pobieramy całość i filtrujemy lokalnie.

## 16. Weryfikacja duplikatów danych wejściowych (D-007)

Cel: żaden obiekt nie jest liczony, oceniany ani wysyłany do LLM dwa razy, a każda decyzja o połączeniu ma zapisany powód.

### Trzy różne sytuacje, których nie wolno mylić

| Sytuacja | Przykład | Co robimy |
|---|---|---|
| **Duplikat**: ten sam dokument | ten sam artykuł w Bibliotece Nauki i OpenAIRE; patent EP w wersji A1 i B1 | łączymy w jeden klaster, zostaje jeden rekord kanoniczny |
| **Powiązanie**: ta sama innowacja, inny rodzaj dowodu | artykuł → patent → projekt tej samej uczelni | **nie** łączymy jako duplikat; to łańcuch dowodów (krok 6 i 8) |
| **Podobne rozwiązanie z innej instytucji** | dwie gminy opracowały ten sam sposób dowozu seniorów | nie łączymy; zapisujemy jako „podobne” i pokazujemy jako **ryzyko dublowania prac** (to jeden z mechanizmów z §3 treści) |

### Gdzie w potoku
- **Warstwa 1** w `harvest` (od razu przy pobraniu).
- **Warstwy 2–4** w osobnym etapie `dedup` po `resolve_org`, przed `prefilter` i LLM: oszczędza koszt modelu i nie ocenia tego samego dwa razy.
- **Warstwa 5** po `extract`, na kartach innowacji.

Kolejka: `harvest` → `normalize` → `resolve_org` → **`dedup`** → `link` → `prefilter` → `extract` → **`similar`** → `maturity` → `export`.

### Warstwy wykrywania

1. **Ten sam rekord pobrany ponownie** (w obrębie źródła)
   - Klucz `(source, record_id)`. Ten sam `content_hash` → `unchanged`, rekord nie idzie dalej. Inny hash → nowa wersja, przetwarzamy ponownie od `normalize`. Nagłówek OAI `deleted` → `deleted`.
   - Ważne dla Biblioteki Nauki: stare artykuły dostają nowy `datestamp` przy zmianie metadanych (sprawdzone: artykuły z 2017 r. ze znacznikiem z 2026-10-22), więc bez hasha przetwarzalibyśmy je od nowa.
2. **Ten sam obiekt po identyfikatorze** (między źródłami i w obrębie źródła)
   - Publikacje: DOI ujednolicony (małe litery, bez `https://doi.org/`). W Bibliotece Nauki DOI ma ok. połowa rekordów.
   - Patenty: publikacje A1, A2, A3, B1 tego samego zgłoszenia to jeden wynalazek, grupujemy po numerze zgłoszenia, a dalej po rodzinie patentowej (`familyMemberOf` z EPO Linked Data).
   - Projekty: kod projektu (OpenAIRE `code`, RAD-on `projectNumber`) i grantodawca.
   - Organizacje: wspólny `org_id` z rejestru (ROR, Wikidata, REGON), żeby „PRz” i „Politechnika Rzeszowska im. I. Łukasiewicza” były jedną instytucją.
3. **Prawie duplikaty bez wspólnego identyfikatora**
   - Kandydaci tylko w „blokach”: ten sam `org_id` albo ten sam rok ±1 albo ta sama klasa (FOS, CPC). Dzięki temu nie porównujemy każdego z każdym.
   - Tytuł ujednolicony (bez polskich znaków, interpunkcji i słów pomocniczych) + rok + organizacja; podobieństwo tytułów (Jaccard na słowach) i abstraktów (MinHash na 5-gramach słów).
   - Wersja polska i angielska tego samego artykułu: porównanie przez tytuł w drugim języku, jeśli źródło go podaje, inaczej warstwa 4.
4. **Duplikaty semantyczne**
   - Embeddingi wielojęzyczne tytułu i abstraktu, podobieństwo kosinusowe w tych samych blokach.
   - Progi startowe (do kalibracji na zbiorze testowym): ≥ 0,95 i ta sama organizacja → łączymy automatycznie; 0,85–0,95 → `needs_review` z parą do porównania; < 0,85 → różne.
   - LLM tylko jako sędzia w przedziale przeglądu: dostaje dwa rekordy i odpowiada „ten sam dokument / ta sama innowacja, inny dowód / różne”, z cytatem. Nie łączy sam.
5. **Podobne rozwiązania między instytucjami** (po `extract`)
   - Porównanie kart: `solution_name` + `problem_solved` (embeddingi), różne `org_id`.
   - Wynik: lista „podobne rozwiązania” na karcie i flaga „możliwe dublowanie prac” z datami (kto był pierwszy).

### Co zostaje zapisane
- **Para:** dwa `record_id`, warstwa, metoda, wynik podobieństwa, decyzja (`duplicate | related | similar | distinct | needs_review`), powód po polsku.
- **Klaster:** `cluster_id`, rekord kanoniczny, lista członków ze źródłami.
- **Wybór rekordu kanonicznego:** najpełniejszy opis, abstrakt po polsku, otwarta licencja, identyfikator (DOI), najnowsza wersja.
- **Scalanie:** pola z rekordu kanonicznego, braki uzupełniane z pozostałych, **wszystkie linki do źródeł zostają** (to, że coś występuje w kilku bazach, jest informacją).

### Liczniki (bez pominięć, D-005)
Na etap `dedup`: przyjęte = nowe + nowe wersje + bez zmian + połączone jako duplikat + do przeglądu. Ekran operatora pokazuje te liczby i listę par do przeglądu.

### W uzasadnieniu dla urzędnika
Punkt 1 „Co ustalono” dostaje wiersz o duplikatach, np.:
- „Ten sam artykuł występuje w Bibliotece Nauki i OpenAIRE (DOI 10.xxxx), połączono w jedną kartę.”
- „Publikacje EP A1 i B1 to jedno zgłoszenie patentowe.”
- „Podobne rozwiązanie opracowała Gmina X w 2021 r.: możliwe dublowanie prac, warto się skontaktować.”

### Narzędzie agenta
`find_duplicates(record_id)` zwraca klaster, pary z decyzjami i podobne rozwiązania; agent nie może połączyć rekordów sam, tylko odczytać wynik etapu `dedup`.

### Sprawdzenie jakości
Zbiór testowy 40 par (20 duplikatów, 20 nie): mierzymy precyzję i czułość wykrywania przy każdej zmianie progów. Do pitchu: liczba z tego zbioru, np. „wykrywanie duplikatów: precyzja 95% na 40 parach”.
