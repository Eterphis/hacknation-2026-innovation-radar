# Ścieżki użytkowników i wartość biznesowa

Radar nie jest katalogiem. Każda osoba przychodzi z jedną decyzją do podjęcia, a aplikacja ma ją do tej decyzji doprowadzić w kilku krokach: **zobacz → zrozum → zapisz → działaj**.

## Zasady UI

1. **Na wejściu jedna obietnica i jedna akcja.** Strona główna pokazuje hasło, przycisk „Dopasuj w 30 sekund”, 3 liczby, 6 grup odbiorców i 6 propozycji „Na dziś”. Reszta (mapa, trendy, klastry) jest niżej albo w osobnych zakładkach.
2. **Szczegóły na żądanie.** Pomysł ma własną stronę (`#/pomysl/<id>`, link można wysłać): u góry tytuł, 4 liczby i akcje, a dalej zakładki: Biznes, Dla inwestora, Jak wdrożyć, Ryzyka, Podobne, Źródło.
3. **Każdy pomysł można zapisać i ocenić.** Zakładka (zapis w przeglądarce, lista w Portfel → Zapisane) i serce, które jest oceną społeczności (anonimowo, liczone na serwerze, sortowanie „ocena społeczności”).
4. **Bez rozciągniętych pól.** Listy w siatce `auto-fill`, karty o stałym rytmie, „Załaduj więcej” i doładowanie przy przewijaniu.
5. **Ruch tylko tam, gdzie coś znaczy.** Granica Polski rysuje się podczas ładowania, pasek postępu przy zmianie widoku, płynne przejścia między pytaniami kreatora, licznik KPI. Respektujemy `prefers-reduced-motion`.
6. **Polskie barwy.** Biel i czerwień na beżu, czerń dla kontrastu; jedna rodzina ikon (Lucide). Ilustracje z Higgsfield są oznaczone jako AI.

## Ścieżki (kreator „Dopasuj” rozgałęzia się po pierwszym pytaniu)

| Kto | Decyzja, którą podejmuje | Pytania po „Kim jesteś?” | Co widzi najpierw | Następny krok |
|---|---|---|---|---|
| Inwestorzy i firmy | czy wejść kapitałowo / licencją | ticket → branże (wiele) → etap wejścia → region (opcjonalnie) | wartość licencji / spin-off, gotowość inwestycyjna, IP, trakcja | Portfel (lejek: kontakt → DD → term sheet), memo PDF |
| Samorządy i instytucje | czy wdrożyć u siebie i za ile | typ instytucji (gmina / powiat / szpital / inna) → województwo → co chcesz poprawić (wiele) → budżet | koszt kopii, oszczędność vs budowa od zera, zwrot, program finansowania | Wdrożenia: kto wdroży + specyfikacja wdrożenia |
| Uczelnie i jednostki naukowe | jak skomercjalizować wynik / z kim | cel (komercjalizacja / partner / grant) → dziedziny → region | tantiemy, odbiorcy, podobne prace (dublowanie) | partner w Wdrożeniach, zgłoszenie do TTO |
| Szkoły i placówki | co sprawdzonego przenieść do szkoły | typ placówki → obszary (edukacja zawsze) → budżet (niski/średni) → region | tanie, gotowe programy z innych szkół | specyfikacja wdrożenia, FERS |
| Startupy i przedsiębiorstwa | gdzie jest rynek / technologia | czego potrzebujesz (licencja / popyt publiczny / skalowanie / finansowanie) → branże → region → budżet | TAM/SAM/SOM, odbiorcy, partnerzy naukowi | Wdrożenia (wykonawca): mapa przychodu |
| Indywidualni innowatorzy | czy mój pomysł ma sens i skąd pieniądze | etap pomysłu → czego dotyczy → czego szukasz → region | podobne pomysły i jak zrobiły następny krok, programy | alerty RSS, akcelerator PCI |

Profil zostaje w przeglądarce; z wyników da się zasubskrybować kanał nowych dopasowań (bez logowania i e-maila).

## Procesy, które aplikacja obsługuje

- **Inwestor:** odkrycie → zapis → porównanie 2–4 → memo → lejek (nowe → kontakt → due diligence → term sheet) → alert o nowych w tezie.
- **Zamawiający publiczny:** problem → gotowe rozwiązania z kosztem kopii → kto wdroży (twórca + dostawcy w sektorze) → z czego zapłacić → specyfikacja do zapytania ofertowego.
- **Wykonawca:** mapa województw (przychód 3 lata / lokalna konkurencja) → rozwiązania do licencji → kontakt z twórcą.
- **Operator PCI:** źródła → Basal → karta → decyzja (zatwierdź / odrzuć) → monitoring w Grafanie.

## Pomysły warte wdrożenia (kolejne kroki)

1. **Teczka zamówienia publicznego:** z karty generowany opis przedmiotu zamówienia, kryteria oceny ofert i lista potencjalnych wykonawców (dla samorządów: oszczędza tygodnie).
2. **Dopasowanie dwustronne:** potrzeby samorządów (z kreatora, zanonimizowane i zagregowane) widoczne dla wykonawców i uczelni jako „popyt”: mapa popytu vs podaży.
3. **Sygnał społeczności:** polubienia + zapisy + dodania do portfela jako wskaźnik popytu; „Na fali w Twoim województwie”.
4. **Tydzień w radarze:** cotygodniowy skrót (RSS / webhook) per profil: nowe dopasowania, pomysły, które dojrzały, zmiany wycen.
5. **Porównanie z „zrób to sam”:** kalkulator: koszt budowy od zera vs kopia + licencja, z czasem do uruchomienia.
6. **Ścieżka grantowa:** dla pomysłu i instytucji lista naborów (FENG, FERS, regionalne) z terminami i dopasowaniem kryteriów.
7. **Klastry jako tezy inwestycyjne:** „AI w zdrowiu”, „Materiały w przemyśle” z wielkością rynku, dojrzałością i czołowymi zespołami: gotowy materiał dla funduszu.
8. **Demo głosowe (później, ElevenLabs):** lektor czyta rolkę / memo.
