# Scenariusz walidacji a–e (2 przypadki)

Wymaganie zadania: a) wprowadzenie / wykrycie innowacji, b) uporządkowanie informacji, c) ocena potencjału, d) wskazanie odbiorców, partnerów i ścieżek, e) uzasadnienie rekomendacji.

## Przypadek 1: zgłoszenie (szkoła z Podkarpacia), na żywo

| Krok | Gdzie | Co widać |
|---|---|---|
| a) wprowadzenie | `#/zglos` → „Wyślij do radaru” | etapy potoku zapalają się na żywo; zgłoszenie ma priorytet 9 i nie może zostać odrzucone po cichu |
| b) uporządkowanie | ekran śledzenia, potem `#/pomysl/<id>` | sektor, typ innowacji, instytucja, województwo (Basal), karta: problem, co nowego, odbiorcy, z cytatami ze źródła |
| c) ocena | strona pomysłu → zakładka „Źródło i ocena” | 6 jawnych kryteriów z wagami i uzasadnieniem, wynik 0–100, dojrzałość (4 poziomy) |
| d) odbiorcy i ścieżki | zakładki „Jak wdrożyć” i „Biznes”, `#/wdrozenia` | ścieżka (np. transfer do innej organizacji), kroki i kto je robi, typy odbiorców, programy finansowania, kto może wdrożyć |
| e) uzasadnienie | zakładki „Dla inwestora”, „Ryzyka”, memo PDF | gotowość inwestycyjna z rozbiciem, korekta wyceny z powodami, ryzyka i mitygacje, mierniki skuteczności, założenia wyceny |

## Przypadek 2: wykrycie automatyczne (historia sukcesu NCBR, szpital w Gdańsku)

| Krok | Gdzie | Co widać |
|---|---|---|
| a) wykrycie | `#/zrodla` (harvester NCBR), `/metrics` | rekord pobrany bez udziału człowieka, przyrostowo, z kursorem |
| b) uporządkowanie | `#/pomysl/<id>` | Basal: „Opieka zdrowotna”, „Oprogramowanie i e-usługi”, instytucja z rejestru RAD-on |
| c) ocena | ring oceny, kryteria | wynik ok. 77, dojrzałość „gotowe do wdrożenia” |
| d) odbiorcy | „Biznes”, `#/wdrozenia?side=odbiorca&voivodeship=pomorskie` | 950 szpitali (odbiorcy), koszt kopii ok. 137 tys. zł, programy (FERS, regionalne FE), dostawcy w sektorze |
| e) uzasadnienie | memo (`/api/cards/<id>/memo`) i specyfikacja wdrożenia (`?kind=wykonawca`) | jedna strona do wysłania inwestorowi lub zamawiającemu, z założeniami i źródłem |

Oba przypadki działają bez żadnego klucza LLM (reguły) i bez internetu po stronie przeglądarki.
