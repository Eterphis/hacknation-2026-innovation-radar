# Dziennik decyzji

Każda decyzja, która zmienia kierunek, zakres albo zasady pracy. Najnowsze na dole.
Format wpisu: nagłówek drugiego poziomu `D-<kolejny numer, 3 cyfry> <krótki tytuł>`, pod nim:

```
- **Decyzja:** …
- **Dlaczego:** …
- **Kto:** człowiek | judge | coordinator
- **Data:** YYYY-MM-DD HH:MM
```

## D-001 Spec z intake PCI zatwierdzony
- **Decyzja:** Wszystkie pola `proposed` w spec.yaml z intake (rubryka etapów I i II, zasady, deliverables, źródła danych, cel, użytkownicy) obowiązują. Etap II to TOP 3; licencja EUPL-1.2; film ≤ 3 min, PDF ≤ 10 slajdów.
- **Dlaczego:** Pola wzięte wprost z treści zadania i regulaminu zadania PCI (odpowiedź A na Q-001).
- **Kto:** człowiek
- **Data:** 2026-11-21 11:37

## D-002 Ustalenie z mentorami: radar sam wyszukuje pomysły w bazach danych
- **Decyzja:** System ma sam wyszukiwać pomysły w bazach danych (np. tych z §7 treści zadania: UPRP, EPO, PBN, PPM, biblioteki cyfrowe PAN i BazTOL, Interreg, NCBR) i dalej je przetwarzać (porządkowanie, ocena, ścieżka, odbiorcy). Ręczne zgłoszenie może być dodatkiem, nie rdzeniem. Pomysły z rundy 1 bez pobierania z baz (I-001, I-003, I-005 jako rdzeń) odpadają jako kierunek główny; Q-003 zastąpione przez Q-004 (runda 2).
- **Dlaczego:** Ustalenie z mentorami PCI przekazane przez człowieka 2026-11-21.
- **Kto:** człowiek
- **Data:** 2026-11-21 12:05

## D-003 Wymagania architektury (dotyczą każdego wariantu z Q-004)
- **Decyzja:**
  1. Wdrożenie na Kubernetes przez Helm charts.
  2. Przetwarzanie w workerach z zabezpieczeniem przed pominięciem: żaden pobrany rekord nie może zginąć ani zostać przetworzony „po łebkach” (interpretacja coordinatora, do potwierdzenia w Q-006).
  3. Kolejkowanie: RabbitMQ + Celery.
  4. Podmienialne API do LLM z fallbackiem.
- **Dlaczego:** Wymaganie człowieka 2026-11-21; wzmacnia kryterium C5 (skalowalność na wiele organizacji, integracje, rozwój po hackathonie, treść §5).
- **Kto:** człowiek
- **Data:** 2026-11-21 12:22

## D-004 Wybór pomysłu: wariant A z Q-004 (domyślny po terminie)
- **Decyzja:** Budujemy I-006 (lejek radaru) jako szkielet, I-007 w lekkiej wersji (dojrzałość z dowodów, proste łączenie z widoczną pewnością) i paszport transferu (I-004/I-009) na wyjściu.
- **Dlaczego:** Termin Q-004 (13:30) minął bez odpowiedzi; protokół przyjmuje „Domyślnie” (rekomendacja judge, szacunkowo 22/25). Człowiek może cofnąć.
- **Kto:** judge
- **Data:** 2026-11-21 13:27
- **Korekta (13:28):** wpis przedwczesny, termin 13:30 jeszcze nie minął. Decyzja nie obowiązuje, dopóki człowiek nie odpowie albo nie minie termin.
- **Status (13:36):** termin minął, ale wybór zastąpiony przez rundę ideacji 3 (D-006, Q-007). Nie obowiązuje.

## D-005 Architektura: wariant A z Q-006 (domyślny po terminie)
- **Decyzja:** „Bez pominięcia sensu” = (a) żaden rekord nie ginie w kolejce + (b) walidacja wyniku LLM z cytatem ze źródła dla każdego pola. Dla jury ścieżka docker compose; Helm chart testowany na k3d, publiczny URL tylko jeśli starczy czasu.
- **Dlaczego:** Termin Q-006 (13:30) minął bez odpowiedzi; protokół przyjmuje „Domyślnie”. Człowiek może cofnąć.
- **Kto:** judge
- **Data:** 2026-11-21 13:27
- **Korekta (13:28):** wpis przedwczesny, termin 13:30 jeszcze nie minął. Decyzja nie obowiązuje, dopóki człowiek nie odpowie albo nie minie termin.
- **Status (13:36):** termin 13:30 minął bez odpowiedzi, więc decyzja obowiązuje. Człowiek może cofnąć.

## D-006 Wymagania rundy 3: aplikacja webowa + agent AI z tokiem rozumowania dla urzędnika
- **Decyzja:** Produkt to aplikacja webowa z agentem AI. Przepływ: pobranie danych z zewnętrznych źródeł (np. API) → parsowanie → przetwarzanie → ocena → klasyfikacja „do czego i dla kogo” → wynik razem z tokiem rozumowania w formie zrozumiałej dla urzędnika. Wejście i wyjście to cel i pytania z treści zadania §2 (gdzie i jak szukać, jakie informacje zbierać, jak oceniać potencjał, jak połączyć z odbiorcą). Nowa runda ideacji (Q-007) zastępuje wybór z Q-004; D-002, D-003 i D-005 dalej obowiązują.
- **Dlaczego:** Wymaganie człowieka 2026-11-21 13:36.
- **Kto:** człowiek
- **Data:** 2026-11-21 13:36

## D-007 Weryfikacja, czy dane wejściowe się nie duplikują
- **Decyzja:** Przed przetwarzaniem przez LLM każdy rekord przechodzi etap `dedup`: ten sam rekord pobrany drugi raz, ta sama praca w kilku źródłach i bardzo podobne opisy są wykrywane i łączone w jeden klaster, a decyzja (połączone / do przeglądu / różne) jest zapisana z powodem i widoczna w uzasadnieniu dla urzędnika. Projekt etapu: `reports/pipeline-design.md` sekcja 16.
- **Dlaczego:** Wymaganie człowieka 2026-11-21. Duplikaty zawyżają liczbę „znalezionych innowacji”, psują ocenę (ten sam pomysł oceniony kilka razy inaczej) i podnoszą koszt LLM.
- **Kto:** człowiek
- **Data:** 2026-11-21 13:43

## D-008 Wybór z Q-007 po przepytaniu (wariant A z zawężeniami)
- **Decyzja:**
  1. Rdzeń: I-011 (agent-analityk z uzasadnieniem w układzie decyzji urzędowej). Główny bohater demo: **operator PCI**, pierwszy ekran to kolejka innowacji znalezionych przez radar.
  2. I-012 („opisz potrzebę”) i recenzent z I-014 („Co przemawia przeciw”): **po golden path**, nie w MVP na 18:00.
  3. Źródła golden path: te, które wystarczą do kryteriów zadania i dalszego przetwarzania, czyli **RAD-on** (rejestr uczelni i instytutów, status publiczny, projekty NCN/NCBR), **Biblioteka Nauki** (kandydaci z opisem), **EPO Linked Data** (patenty EP, dowód gotowej technologii), **Kohesio** (samorządy, innowacje nietechnologiczne, ślad wdrożenia, beneficjenci jako katalog odbiorców). OpenAIRE wieczorem. Szkoły (RSPO) zostają luką.
  4. Dwa przypadki demo: **technologia z uczelni** (artykuł + patent EP, brak wdrożenia) i **rozwiązanie gminy** z Kohesio do przeniesienia do innych gmin.
  5. Akcja operatora: **zatwierdź / odrzuć** kartę; bez szkicu pisma i bez wysyłki.
  6. Zakres danych: **cała Polska**.
  7. Dostawca LLM: do ustalenia później; teraz priorytet to pozyskanie danych dobrej jakości.
  8. Zbiór testowy: do ustalenia po uruchomieniu pozyskiwania danych.
- **Konsekwencje (coordinator):** przy całej Polsce pobieranie musi być przyrostowe i stronicowane (Biblioteka Nauki ma całe archiwum w OAI-PMH, RAD-on ok. 49 tys. projektów), z filtrem regionu w interfejsie zamiast przy pobieraniu; do golden path wystarczy pierwsza partia z każdego źródła, a pełne pobranie działa w tle.
- **Dlaczego:** Odpowiedzi człowieka w przepytaniu Q-007, 2026-11-21.
- **Kto:** człowiek
- **Data:** 2026-11-21 13:55

## D-009 Feed rolek z głosowaniem w zakresie, po golden path
- **Decyzja:**
  1. Podział źródeł na typy (transport, rola, rodzaj, dostępność) i wspólny format `Signal` v1 jako jedyne wejście dalszych etapów obowiązują (`reports/sources-and-idea-flow.md` §2–3).
  2. Przepływ po `dedup`: `gate` (Basal Omni) → `IdeaTask` → agent-analityk (pomysł, innowacyjność, klient, model biznesowy, wykonalność SDLC, ryzyka i mitygacje) → recenzent → brief → propozycja → zatwierdzenie operatora PCI (§4–8).
  3. **Feed rolek z polubieniami, głosami i rankingiem wchodzi do zakresu przed oddaniem (22.11 11:00), ale dopiero po golden path** (krok 5 planu w §11). Generowanie AI dla top-N (krok 6) tylko jeśli starczy czasu; na pitch wystarczy jeden przykład.
  4. Kto głosuje i czym jest Basal: rozstrzygnięte w D-010.
- **Dlaczego:** Odpowiedź człowieka 2026-11-21 na pytanie 1 z `reports/sources-and-idea-flow.md` §12. Rozszerza D-008 (zatwierdź/odrzuć zostaje, feed widzi tylko zatwierdzone karty).
- **Kto:** człowiek
- **Data:** 2026-11-21 14:25

## D-010 Basal bez LLM, publiczna platforma z głosowaniem, filmiki jako boost
- **Decyzja:**
  1. **Basal** (etap `gate`) działa bez LLM: odsiewa nieodpowiednie zgłoszenia (spam, treść obraźliwa, za mało informacji, poza zakresem, duplikat, dane osobowe) i sortuje resztę według typów z treści zadania (typ instytucji, typ innowacji, dojrzałość wstępna). Wynik to klucz routingu i priorytet w kolejce RabbitMQ, żeby LLM dostawał tylko to, co przeszło, w kolejności priorytetu (`reports/sources-and-idea-flow.md` §5).
  2. **Demo oceniają użytkownicy:** platforma z rolkami jest publiczna; oglądanie bez konta, głos po lekkiej rejestracji, jedna osoba = jeden głos, równa waga (§9).
  3. **Filmiki AI** tylko promują (boost) pomysły z czołówki rankingu głosów, w obrębie typu; wejście z zatwierdzonego briefu, oznaczenie „wizualizacja AI” (§10).
- **Dlaczego:** Odpowiedź człowieka 2026-11-21 na pytania 2–3 z §12 raportu: zadań w kolejce może być dużo, LLM nie może się na nie marnować; „żyjemy w demokracji”.
- **Kto:** człowiek
- **Data:** 2026-11-21 14:35
