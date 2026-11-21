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
