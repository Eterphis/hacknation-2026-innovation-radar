"""Crawler stron i dokumentów bez LLM: strona/PDF -> czysty tekst + metadane -> rekord radar.record/v1.

Moduły: `sites` (lista witryn z config/sites.json), `fetcher` (robots.txt, limit na host, zapytania
warunkowe, wykrywanie blokad), `frontier` (kanoniczne URL-e, zakres, sitemapy, kolejka w bazie),
`extract` (główny tekst, metadane, linki, PDF), `classify` (rodzaj strony i sygnały innowacyjności
ze słowników), `normalize` (rekord), `crawler` (przejście witryny) i CLI `python -m radar.crawl`.
"""
