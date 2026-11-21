# Główne flow radaru (wersja robocza 2026-11-21)

- **Autor:** sesja budująca `app/` (Helm/Celery), na prośbę człowieka
- **Powiązane:** `pipeline-design.md` (etapy), `sources-and-idea-flow.md` (Signal v1, Basal, IdeaTask, feed; D-009, D-010)
- **Kod:** `app/radar/basal/` (klasyfikator, embeddingi, graf), `app/radar/pipeline/assess.py` (agent wdrożeniowy), `app/radar/api/` (eksploracja, rolki)

```
 1. WEJŚCIE            2. BASAL (bez LLM, ms/rekord)          3. AGENT WDROŻENIOWY (LLM + narzędzia)      4. PREZENTACJA
 pull/push/formularz → normalize → dedup → gate ───────────► assess ──► Basal-recheck ──► ranking ──────► eksploracja, graf,
                                            │ accept/hold/reject │ narzędzia: podobne,   │ spójność      │ mapa, macierz,
                                            │ sektor, obszar     │ kontekst regionu,     │ ścieżki z     │ rolki (briefy)
                                            │ technologii, typ,  │ odbiorcy, Basal       │ dojrzałością, │ + polubienia
                                            │ dojrzałość, koszt, │                       │ koszt vs      │
                                            │ priorytet          │ ryzyka + mitygacje,   │ instytucja    │
                                            └ index: embedding + graf (krawędzie)        kto co może zrobić
```

## 1. Wejście danych
Bez zmian względem `app/sources.yaml`: pull (REST, GraphQL, OAI-PMH, SPARQL, snapshot), push (webhook, AMQP, Pub/Sub, Kafka), formularz. Konektory i crawler z gałęzi `feature/pobieranie-danych` (NCBR, Interreg, strony www) dołączamy jako kolejne źródła (`snapshot` z ich JSONL albo bezpośrednio).

## 2. Basal: jeden przebieg, wiele osi
Tak, odrzucanie/przyjmowanie i sektor da się klasyfikować od razu, w jednym przebiegu. Basal zwraca dla każdej osi etykietę, pewność i dowód (które słowa lub który prototyp zadecydował):

| Oś | Wartości | Skąd |
|---|---|---|
| decyzja | accept / hold / reject (+ powody) | reguły jakości, negatywne sygnały, PII, spam, „tylko firma prywatna” |
| sektor gospodarki | sekcje PKD (rolnictwo, przemysł, energetyka, woda i odpady, budownictwo, transport, ICT, nauka, administracja, edukacja, zdrowie, kultura) | słowniki + podobieństwo do opisów sekcji |
| obszar technologii | AI i dane, IoT/czujniki, energia i wodór, materiały/kompozyty, lotnictwo i kosmos, motoryzacja, biotech/medtech, agro/żywność, środowisko, budownictwo, oprogramowanie/e-usługi, robotyka, metody nietechnologiczne | j.w. |
| typ innowacji | technologiczna, organizacyjna, edukacyjna, społeczna, procesowa, usługowa | j.w. |
| typ instytucji | szkoła, uczelnia, instytut, JST, inna publiczna, firma, unknown | pole zgłoszenia, afiliacje, słowniki (docelowo rejestr z `resolve_org`) |
| dojrzałość wstępna | exploring … market_ready | sygnały (prototyp, pilotaż, patent, wdrożenie) |
| poziom kosztów | niski / średni / wysoki / bardzo wysoki | kwoty z rekordu, inaczej słowa (infrastruktura, laboratorium, oprogramowanie) |
| województwo | 16 województw | region, afiliacje, miasta |

Klasyfikator ma trzy warstwy, które działają na zwykłym vCPU:
1. **Słowniki i reguły** (zawsze, deterministyczne, wyjaśnialne).
2. **Prototypy w przestrzeni embeddingów**: każda etykieta ma opis; podobieństwo kosinusowe rekordu do opisu. Domyślny embedder to hashing n-gramów znakowych (numpy, zero pobierań); lepszy to `intfloat/multilingual-e5-small` przez fastembed/ONNX (~120 MB, CPU), włączany `RADAR_EMBEDDER=fastembed`.
3. **Uczony nagłówek decyzji**: regresja logistyczna (numpy) na decyzjach operatora (zatwierdź/odrzuć), `radar basal-train`. Im więcej decyzji, tym bardziej Basal przypomina operatora.

Basal działa **dwa razy**: przed LLM (bramka i routing) i po agencie (sprawdza spójność jego wniosków z regułami).

## 3. Agent wdrożeniowy (`assess`)
Wejście: karta + wynik Basala. Narzędzia (kod, bez LLM): `find_similar` (graf/embeddingi), `regional_context` (co już jest w województwie i sektorze, luki), `recipients` (instytucje z danych w tym sektorze/regionie, beneficjenci), `basal_check`.
Wyjście `Assessment`: ścieżki wdrożenia z „kto co robi”, ryzyka z mitygacjami i właścicielem, odbiorcy z uzasadnieniem, oceny 0–5 na kryteria (dojrzałość, przenaszalność, skala problemu, koszt, siła dowodów, nowość) i wynik łączny do rankingu.
Bez klucza działa wersja regułowa (te same pola). Z LLM (chmura albo lokalny model) agent dopisuje uzasadnienia; Basal-recheck odrzuca twierdzenia sprzeczne z danymi.

## 4. Wyszukiwanie i prezentacja
- Filtry i fasety: sektor, obszar technologii, typ innowacji, typ instytucji, województwo, dojrzałość, koszt, wynik, decyzja, pełny tekst.
- **Graf** jak w Obsidianie: węzły = pomysły + huby (sektor, obszar, województwo, instytucja), krawędzie = podobieństwo i wspólne cechy.
- **Mapa** (kartogram 16 województw) i **macierz** województwo × sektor: liczba pomysłów, udział względem średniej krajowej, **luka** (sektor słabo reprezentowany w regionie względem kraju = szansa na transfer).
- **Rolki**: jednostronicowe briefy przewijane pionowo, polubienia (jeden głos na przeglądarkę, D-010 docelowo konto).

## 5. Lekki model na VPS
- Embeddingi: hashing (domyślnie) albo `multilingual-e5-small` ONNX (CPU, ~10–30 ms na tekst).
- LLM lokalny do sprawdzania i uzasadnień: **Bielik 1.5B v3.0 Instruct GGUF** (polski, Apache-2.0) w `llama.cpp server` (OpenAI-compatible) na CPU; większy wariant 4.5B, gdy VPS ma ≥ 8 GB RAM. W compose profil `local-llm`, w Helm `localLLM.enabled`. Router: `RADAR_LLM_PROVIDERS=local,anthropic,mock`.
- Skalowanie: worker `llm` ma osobną kolejkę i własną liczbę replik; Basal i indeks działają na workerze `ingest`.

## Graf: dlaczego Postgres, a nie osobna baza grafowa
Przy tysiącach–dziesiątkach tysięcy węzłów tabela krawędzi + zapytania rekurencyjne (głębokość 2–3) w Postgresie odpowiadają w milisekundach, bez dodatkowej usługi. Kùzu został zarchiwizowany w 10.2025; Apache AGE (Cypher w Postgresie) ma sens dopiero przy głębokich przejściach na >100 tys. węzłów. pgvector można dołożyć później do podobieństwa po stronie bazy.
