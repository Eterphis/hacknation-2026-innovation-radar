# Fixture OpenAlex

`works_page1.json` i `works_page2.json` to dwie strony odpowiedzi `GET https://api.openalex.org/works`
(paginacja kursorem: strona 1 ma `meta.next_cursor`, strona 2 `null`).

**Uwaga:** przy budowie konektora (2026-11-21) API odpowiadało `429 daily_budget` (wyczerpany darmowy
budżet dzielony na adres IP), więc pliki odtworzono ręcznie według struktury odpowiedzi OpenAlex
(pola `meta`, `results[]`, `authorships[].institutions[]`, `abstract_inverted_index`, `topics`, `keywords`,
`primary_location`, `open_access`, `grants`). Identyfikatory (`W44000000…`, `00example…`), DOI `10.0000/…`
i nazwiska autorów są fikcyjne. Strona 2 celowo zawiera duplikat pracy ze strony 1 i rekord bez abstraktu.

Podmiana na realną odpowiedź (bez danych osobowych użytkownika: `OPENALEX_MAILTO`/`OPENALEX_API_KEY`
są usuwane z zapisanych adresów):

```powershell
python -X utf8 -m radar.sources.openalex --limit 3 --raw-dir $env:TEMP\oa --out $env:TEMP\oa.jsonl
```

Potem skopiuj `$env:TEMP\oa\pages\page-0001.json` jako `works_page1.json` i dostosuj asercje w
`tests/test_openalex.py`, które odwołują się do konkretnych prac.
