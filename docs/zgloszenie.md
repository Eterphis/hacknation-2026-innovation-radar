# Zgłoszenie HackNation 2026: Radar Innowacji (zespół Eterphis, stolik 16c)

## Problem
Szkoły, uczelnie, samorządy i instytuty codziennie tworzą dobre rozwiązania: technologiczne, ale też organizacyjne, edukacyjne, społeczne i procesowe. Większość z nich nigdy nie wychodzi poza miejsce, w którym powstała. Informacje o nich są rozproszone po dziesiątkach źródeł: bazach projektów (NCBR, Kohesio, Interreg, CORDIS, RAD-on), repozytoriach publikacji (Biblioteka Nauki, OpenAIRE), bazach patentowych (EPO, UPRP) i stronach instytucji. Nie ma jednego miejsca, w którym da się je znaleźć, porównać i ocenić, a nikt nie mówi, czy pomysł jest gotowy do wdrożenia, ile kosztuje jego kopia i kto może go wdrożyć.

Skutek: gminy (w Polsce jest ich 2477) i instytucje wymyślają te same rozwiązania od nowa, środki publiczne idą na dublowanie prac, a twórcy nie trafiają do partnerów, odbiorców ani inwestorów. Polska od lat jest w grupie „emerging innovators” w European Innovation Scoreboard, a jednym z powodów jest słaby transfer wiedzy z nauki i sektora publicznego do praktyki.

## Solution
Radar Innowacji to radar, który sam wyszukuje „ukryte” innowacje w publicznych źródłach, ocenia je, wycenia i pokazuje, kto może je wdrożyć. Dziś to ponad 1200 ocenionych pomysłów z 281 instytucji ze wszystkich 16 województw, z 13 automatycznie odświeżanych źródeł.

Co robi system:
- Wykrywanie: konektory do NCBR, Kohesio, Interreg, CORDIS, RAD-on, OpenAIRE, Biblioteki Nauki, EPO i kanałów RSS platform zgłoszeń. Nowy pomysł w źródle radar wykrywa sam, ocenia i po chwili pokazuje gotową kartę. Nowe źródło to jeden wpis w konfiguracji, bez zmian w kodzie.
- Porządkowanie i ocena: deterministyczny potok (normalizacja, deduplikacja, rejestry organizacji). Klasyfikacja, ocena i wycena działają na jawnych regułach, bez płatnych modeli językowych i bez chmury. Lokalny model Bielik 1.5B pracuje tylko w tle (krótkie opisy), nic nie jest generowane na żywo i nic nie jest zmyślone: każde twierdzenie wskazuje fakt ze źródła.
- Wartość biznesowa: na karcie od razu widać koszt wdrożenia u odbiorcy, czas zwrotu i liczbę potencjalnych odbiorców (dane GUS). Technologie wyceniamy wartością licencji, a modele działania (programy szkolne, rozwiązania gmin) oszczędnością odbiorców.
- Dopasowanie w 30 sekund: samorząd, inwestor, uczelnia, szkoła, startup i innowator odpowiadają na kilka pytań i dostają dopasowane rozwiązania z powodami (region, budżet, dojrzałość).
- Narzędzia decyzji: specyfikacja wdrożenia do zapytania ofertowego, memo inwestycyjne PDF, portfel inwestora (lejek od kontaktu do decyzji), porównanie, mapa Polski z lukami, klastry tematyczne, wdrożenia dla wykonawców.
- Rolki: szybki sposób na odkrywanie pomysłów, jeden po drugim; polubienia zbierają opinię społeczności.
- Tryb regionalny: urząd marszałkowski widzi tylko swoje województwo.
- Dostępność: powiększenie tekstu, wysoki kontrast, bez animacji, pełna obsługa klawiaturą, wersja mobilna.

Korzyści: instytucje widzą, co już działa gdzie indziej, i nie dublują pracy. Twórcy dostają jasne „co dalej”. Inwestorzy i firmy znajdują gotowe albo rozwijające się rozwiązania w jednym miejscu. Całość działa na jednym tanim serwerze (ok. 50 zł/mies.) i skaluje się w Kubernetesie.

## What's done so far and goal of your project
Przed wydarzeniem: koncepcja i szkielet potoku danych (raw → normalized → enriched) oraz pierwsze konektory.

Zrobione podczas hackathonu:
- 13 działających źródeł danych z automatycznym odświeżaniem, limitami zapytań i wykrywaniem nowych rekordów; ponad 1200 ocenionych kart innowacji z prawdziwych danych,
- klasyfikator Basal (reguły, ok. 1 ms na rekord), ocena według jawnych kryteriów, wycena biznesowa, sygnały inwestorskie, dopasowanie do 6 grup odbiorców,
- aplikacja webowa i mobilna: przegląd, kreator dopasowania, strona pomysłu, mapa, klastry, rolki, wdrożenia, portfel inwestora, tryb regionalny, panel dostępności,
- wdrożenie: Docker Compose (jedno polecenie), chart Helm z autoskalowaniem (KEDA według kolejek, HPA), Prometheus, Grafana (22 panele) i 8 alertów, publiczny dostęp przez tunel,
- jakość: ok. 200 testów automatycznych, testy UI (Playwright, axe: 0 błędów dostępności), Lighthouse 99 na telefonie, test obciążeniowy na prawdziwych danych: 110 zapytań/s bez błędów na 2 vCPU,
- film demo i prezentacja.

Cel: pilotaż z Podkarpackim Centrum Innowacji na prawdziwych źródłach regionu, cotygodniowy skrót dla samorządów, inwestorów i uczelni oraz specyfikacje wdrożenia prosto do zapytań ofertowych.

## Instrukcje jak otworzyć projekt
- Działająca aplikacja: https://aspects-example-hampton-sunshine.trycloudflare.com (zacznij od „Dopasuj w 30 sekund” albo „Rolki”).
- Monitoring na żywo (Grafana, tylko podgląd): https://rides-pda-boxed-algorithms.trycloudflare.com/d/radar
- Lokalnie: `docker compose up -d --build`, potem http://localhost:8000. Monitoring: `docker compose --profile observability up -d` (Grafana :3000, Prometheus :9090).
- Kubernetes: `helm install radar deploy/helm/innovation-radar --set keda.enabled=true` (opis: docs/kubernetes-i-obserwowalnosc.md).
- Test całego wdrożenia: `python scripts/smoke.py <adres>`.
- Film: docs/film/radar-innowacji-demo.mp4, prezentacja: docs/pitch/pitch.pdf.
