# Scenariusz demo (5 minut)

Ten sam przebieg klika test `e2e/tests/demo.spec.ts` (CI, job `e2e`). Jeśli test jest zielony, każdy krok poniżej
działa na danych demo. Dane: `radar demo` (syntetyczne, oznaczone „przykład”), bez kluczy i bez sieci.

**Przed wejściem na scenę:** otwórz aplikację w oknie incognito (pusty `localStorage`: brak profilu, portfela i zapisów),
1280 × 800 albo rzutnik, motyw jasny (`?theme=light`). Druga karta z `#/klastry` jako zapas. Plan B dla całości:
zrzuty z artefaktu CI `e2e-screens` (`test-results/screens/desktop-light/*.png`) i nagranie zapasowe.

| Czas | Co kliknąć | Co widać | Co powiedzieć | Plan B |
|---|---|---|---|---|
| 0:00–0:30 | Wejdź na stronę główną (`/`). Nic nie klikaj. | Granica Polski rysuje się w loaderze („Szukamy polskich innowacji · 0–100%”), potem hero „Polskie innowacje, które warto wdrożyć”, 3 liczby i „Kim jesteś?”. | „Radar sam przeszukuje publiczne bazy: NCBR, Kohesio, OpenAIRE, uczelnie. Każdy pomysł jest sklasyfikowany bez dużego modelu i wyceniony.” | Loader trwa ≤ 1,5 s; jeśli strona już była otwarta, odśwież (Ctrl+Shift+R). |
| 0:30–1:15 | „Dopasuj w 30 sekund” → „Samorządy i instytucje publiczne” → „Gmina lub miasto” → „pomorskie” → „Pokaż wyniki”. | Kreator: jedno pytanie na ekran, pasek kroku. Wyniki: karty z % dopasowania i powodami („Twój region: pomorskie”, „mieści się w budżecie”). | „Trzy kliknięcia: kim jestem, jaka instytucja, gdzie. Dostaję gotowe rozwiązania z kosztem kopii, nie budowy od zera.” | Jeśli kreator pamięta stary profil: „Zmień odpowiedzi”. Wyniki są też pod `#/dopasuj` po wypełnieniu. |
| 1:15–2:15 | Kliknij kartę z „Twój region: pomorskie” („Magazyn ciepła z piasku dla ciepłowni miejskiej”). Potem „Specyfikacja wdrożenia”. | Strona pomysłu: 4 liczby (wartość licencji, koszt wdrożenia, zwrot, odbiorcy), zakładki Biznes / Dla inwestora / Jak wdrożyć / Ryzyka / Podobne / Źródło. W nowej karcie: specyfikacja wdrożenia z sekcją „Kto może wdrożyć”. | „Specyfikację można od razu dołączyć do zapytania ofertowego: przedmiot, kryteria, kto może to wdrożyć. Wszystko z danych karty, bez zmyślonych faktów.” | Ten pomysł nie jest pierwszy na liście: jest na etapie „technologia gotowa”, a ścieżka samorządu premiuje „gotowe do wdrożenia”. Powiedz to wprost jako zaletę (uczciwy ranking). Zapas: `/api/cards/17/memo?kind=wykonawca`. |
| 2:15–3:30 | Zamknij kartę specyfikacji. Stopka „Grupy odbiorców” albo adres `#/dla/inwestorzy` → pierwsza karta → „Do portfela” → „Memo PDF”. Potem „Portfel” w menu. | Inwestor widzi wartość licencji / spin-off i gotowość inwestycyjną 0–100. Memo inwestycyjne (do zapisania jako PDF). Portfel: lejek Nowe → Kontakt → Due diligence → Term sheet, karta w kolumnie „Nowe”. | „Ten sam pomysł oczami inwestora: gotowość, ochrona IP, trakcja, porównywalne projekty. Jednym kliknięciem memo i lejek transakcji.” | Memo otwiera się w nowej karcie; jeśli przeglądarka blokuje okna, kliknij prawym → „Otwórz w nowej karcie”. |
| 3:30–4:30 | „Klastry” w stopce (`#/klastry`) → klaster „… · Opieka zdrowotna i pomoc społeczna” → „Pokaż najlepsze”. | Cała baza w kilkunastu grupach (technologia × branża), liczba gotowych, województwa, polubienia; po rozwinięciu najlepsze pomysły klastra. | „Dla funduszu i ministerstwa: tematy jako tezy inwestycyjne. Na prawdziwych danych pojawia się tu np. „AI i analiza danych · Opieka zdrowotna”.” | **W danych demo nie ma klastra „AI w zdrowiu”** (brak ≥ 2 pomysłów AI w sektorze zdrowia). Nie obiecuj go na demo; pokaż klaster zdrowia albo tryb „Podobne metody”. |
| 4:30–5:00 | Wróć na Przegląd (logo). | Hero i „Na dziś”. | „Koszt działania poniżej 50 zł miesięcznie na VPS, bez dużego modelu. Kod, testy i raporty jakości są w repozytorium.” | — |

## Co jest sprawdzane automatycznie
`e2e/tests/demo.spec.ts`: loader z granicą Polski widoczny i znika, kreator samorządu z Pomorza daje wyniki z
„Twój region: pomorskie”, strona pomysłu, specyfikacja wdrożenia (`memo?kind=wykonawca`, „Kto może wdrożyć”), pomysł
inwestora w portfelu (kolumna „Nowe”), memo inwestycyjne, klaster zdrowia otwiera się. Brak błędów konsoli i
odpowiedzi ≥ 400 (strażnik w `e2e/fixtures.ts`).

## Luki w danych demo (do decyzji, `.house/QUESTIONS.md`)
- Brak klastra „AI w zdrowiu”: w próbkach jest 1 pomysł `ai_dane` (sektor ICT/energetyka), żadnego w `Q_zdrowie`.
- Jedyny pomysł z Pomorza jest na etapie `tech_ready`, więc w ścieżce samorządu nie wychodzi na pierwsze miejsce.
- Propozycja: dopisać do `app/samples/zgloszenia.jsonl` 2–3 syntetyczne, oznaczone zgłoszenia (AI w diagnostyce /
  rejestracji pacjentów; rozwiązanie z Pomorza gotowe do wdrożenia) i uruchomić cały `pytest` w `app/`, bo próbki
  zasilają inne testy.
