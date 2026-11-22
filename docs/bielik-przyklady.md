# Bielik 1.5B: przykłady narracji przewodników

Wygenerowane 2026-11-22 02:11 lokalnie: Bielik-1.5B-v3.0-Instruct GGUF Q8_0 w llama.cpp, 4 vCPU, bez GPU.
Tekst modelu przyjęty w 6 z 6 przypadków; pozostałe odrzuciła walidacja (nowa liczba, zła długość, niedokończone zdanie) i został tekst z reguł.
Średni czas generowania: 5.1 s na narrację (raz na kartę i przewodnika, potem z pamięci).

## Wnioski

- 1.5B na CPU (~18 tokenów/s na 4 vCPU) dobrze **streszcza i wygładza** listę faktów w 2–3 zdania mówione; gotowy tekst do przepisania tylko kopiuje, więc dostaje fakty punktami, bez tytułu.
- Walidacja odrzuca każdą liczbę spoza faktów i ucięte zdania; wtedy zostaje tekst z reguł. **Nie łapie przekręconego sensu** (zdarza się, np. zamiana słowa w opisie problemu), dlatego narracja jest oznaczona w UI jako „Bielik 1.5B”, a fakty z karty są obok.
- Koszt: zero zł za token; jedna narracja raz na kartę i przewodnika, potem z pamięci w karcie. Dla 1000 nowych kart × 5 przewodników ≈ 10 h CPU w tle albo tylko dla otwieranych kart.
- Lepsza jakość: Bielik 4.5B / 11B (GGUF, 6–12 GB RAM) bez zmian w kodzie (`RADAR_LOCAL_GGUF`).

## Wykorzystanie inżynierii chromosomowej w celu efektywnego transferu segmentów chromosomów nieuprawnych gatunków kozieńcó
Przewodnik: **ada** · źródło tekstu: **bielik-1.5b** · 5.2 s · karta `#1019`

**Fakty (reguły):**

> Cześć, tu Ada, przewodniczka inwestorów. Opowiem o projekcie „Wykorzystanie inżynierii chromosomowej w celu efektywnego transferu segmentów chromosomów nieuprawnych gatunków kozieńcó”, który prowadzi Michał Tomasz Kwiatek (Instytut Genetyki Roślin Polskiej Akademii Nauk w Poznaniu) (województwo opolskie). Celem projektu było wytworzenie nowych genotypów pszenżyta uprawnego odpornych na rdzę brunatną i żółtą powodowane przez grzyby z rodzaju Puccinia. To pomysł gotowy do wdrożenia, gotowość inwestycyjna 39 na 100. Wartość licencji lub spółki szacujemy na 50 milionów złotych, przy szansie wdrożenia 60 procent. Pierwszy krok: ocenić ochronę własności intelektualnej (zgłoszenie patentowe, know-how).

**Narracja:**

> Cześć, tu Ada. Projekt Michała Tomasza Kwiatka z Instytutu Genetyki Roślin PAN w Poznaniu (woj. opolskie) dotyczy produkcji odpornych na rdzę pszenżyta. To gotowy do wdrożenia pomysł, z 39/100 gotowości inwestycyjnej. Wartość licencji/spółki szacowana jest na 50 mln zł, z szansą wdrożenia 60%. Pierwszym krokiem jest ocena ochrony własności intelektualnej (patent, know-how).

## System wspierający organizacje pracy personelu i monitorujący parametry jakości pracy Szpitalnego Oddziału Ratunkowego
Przewodnik: **tomek** · źródło tekstu: **bielik-1.5b** · 5.1 s · karta `#1025`

**Fakty (reguły):**

> Cześć, tu Tomek, przewodnik wdrożeń dla samorządów i wykonawców. Opowiem o projekcie „System wspierający organizacje pracy personelu i monitorujący parametry jakości pracy Szpitalnego Oddziału Ratunkowego”, który prowadzi Uniwersyteckie Centrum Kliniczne w Gdańsku (województwo pomorskie). Z systemu mogą korzystać Szpitale posiadające Oddziały Ratunkowe dla których istotną sprawą są zagadnienia związane z jakością świadczonych usług, obniżeniem poziomu… Wdrożenie u siebie kosztuje około 137 tysięcy złotych, a zwrot to 1–2 lata. Można to sfinansować na przykład z programu FERS. Pierwszy krok: spisać model działania: procedura, role, koszty, umowy (paszport transferu).

**Narracja:**

> Cześć, tu Tomek. Projekt polega na wdrożeniu systemu zarządzania jakością w Szpitalach z Oddziałami Ratunkowymi, który ma na celu poprawę świadczonych usług i obniżenie kosztów. Wdrożenie u siebie kosztuje około 137 tysięcy złotych, a zwrot możliwy jest w ciągu 1-2 lat. Można to sfinansować z programu FERS. Pierwszym krokiem jest spisanie modelu działania: procedury, ról, kosztów i umów (paszport transferu).

## Test jury: drony uczniowskie do inspekcji dachów budynków gminnych
Przewodnik: **ola** · źródło tekstu: **bielik-1.5b** · 5.2 s · karta `#1243`

**Fakty (reguły):**

> Cześć, tu Ola, przewodniczka szkół. Opowiem o projekcie „Test jury: drony uczniowskie do inspekcji dachów budynków gminnych”, który prowadzi Technikum nr 2 (województwo podkarpackie). Uczniowie technikum budują i obsługują drony z kamerą termowizyjną, które sprawdzają dachy szkół i urzędów gminy. Wdrożenie u siebie kosztuje około 600 tysięcy złotych, a zwrot to 1–2 lata. Można to sfinansować na przykład z programu FERS. Pierwszy krok: spisać model działania: procedura, role, koszty, umowy (paszport transferu).

**Narracja:**

> Cześć, tu Ola. Technikum nr 2 w województwie podkarpackim prowadzi projekt, w ramach którego uczniowie budują i obsługują drony z kamerą termowizyjną do kontroli dachów szkół i urzędów. Inwestycja kosztuje około 600 tys. zł, a zwrot po 1-2 latach. Można sfinansować ją z programu FERS. Pierwszym krokiem jest sporządzenie modelu działania (paszportu transferu), określającego procedurę, role, koszty i umowy.

## Studia bez barier - kompleksowy program dostępności Państwowej Uczelni Stanisława Staszica w Pile
Przewodnik: **profesor** · źródło tekstu: **bielik-1.5b** · 4.7 s · karta `#1105`

**Fakty (reguły):**

> Cześć, tu Profesor Marek, przewodnik uczelni i nauki. Opowiem o projekcie „Studia bez barier - kompleksowy program dostępności Państwowej Uczelni Stanisława Staszica w Pile”, który prowadzi Akademia Nauk Stosowanych im. Stanisława Staszica w Pile (województwo opolskie). Projekt przyczynił się do poprawienia dostępności uczelni dla osób z niepełnosprawnościami. Projekt jest gotowy do wdrożenia. Potencjalnych odbiorców jest 21000, to szkół podstawowych i ponadpodstawowych. Następny krok można sfinansować z programu FERS. Pierwszy krok: spisać model działania: procedura, role, koszty, umowy (paszport transferu).

**Narracja:**

> Cześć, tu Profesor Marek. Projekt Akademii Nauk Stosowanych im. Stanisława Staszica w Pile, dotyczący poprawy dostępności uczelni dla osób z niepełnosprawnościami, jest gotowy do wdrożenia. Może być skierowany do 21 000 uczniów szkół podstawowych i ponadpodstawowych. Następny krok to sfinansowanie z programu FERS. Pierwszym krokiem jest spisanie modelu działania: procedura, role, koszty, umowy (paszport transferu).

## New valorisation pathway for chromium tanned leather residues by a combination of protein extraction, chrome recovery an
Przewodnik: **radek** · źródło tekstu: **bielik-1.5b** · 5.1 s · karta `#1111`

**Fakty (reguły):**

> Cześć, tu Radek, przewodnik po radarze. Opowiem o projekcie „New valorisation pathway for chromium tanned leather residues by a combination of protein extraction, chrome recovery an”, który prowadzi PFI, Prüf- und Forschungsinstitut Pirmasens e.V, Niemcy (województwo mazowieckie). Proces produkcji skór wyprawionych jest związany z generowaniem znacznych ilości odpadów. Projekt jest gotowy do wdrożenia, a wdrożenie kosztuje około 343 tysiące złotych. Może z niego skorzystać 8000 odbiorców, czyli zakładów przemysłowych w branży. Pierwszy krok: ocenić ochronę własności intelektualnej (zgłoszenie patentowe, know-how).

**Narracja:**

> Cześć, tu Radek. Projekt związany z produkcją skór wyprawionych, prowadzony przez PFI, Prüf- und Forschungsinstitut Pirmasens e.V., Niemcy (województwo mazowieckie), ma na celu minimalizację odpadów i zwiększenie ochrony własności intelektualnej. Koszt wdrożenia wynosi około 343 tysiące złotych, a skorzysta z niego 8000 odbiorców w branży przemysłowej.

## Eliemental: Innowacje w edukacji przedsiębiorczości dla grup narażonych na wykluczenie społeczne
Przewodnik: **tomek** · źródło tekstu: **bielik-1.5b** · 5.1 s · karta `#99`

**Fakty (reguły):**

> Cześć, tu Tomek, przewodnik wdrożeń dla samorządów i wykonawców. Opowiem o projekcie „Eliemental: Innowacje w edukacji przedsiębiorczości dla grup narażonych na wykluczenie społeczne”, który prowadzi Uniwersytet Łódzki (województwo łódzkie). Wspólnie z badaczami z grup docelowych będziemy współpracować ze społecznościami wrażliwymi na wykluczenie społeczne, aby zmapować aspiracje, potrzeby i możliwości… Wdrożenie u siebie kosztuje około 517 tysięcy złotych, a zwrot to 1–2 lata. Można to sfinansować na przykład z programu NCBR LIDER / Lider. Pierwszy krok: spisać model działania: procedura, role, koszty, umowy (paszport transferu).

**Narracja:**

> Cześć, tu Tomek. Uniwersytet Łódzki prowadzi projekt współpracy z badaczami z grup wrażliwych na wykluczenie społeczne. Celem jest mapowanie aspiracji, potrzeb i możliwości społeczności. Wdrożenie projektu kosztuje około 517 tysięcy złotych, a zwrot po 1-2 latach. Można sfinansować go z programu NCBR LIDER / Lider.
