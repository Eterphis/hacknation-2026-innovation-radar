# Odświeżanie danych (`radar.refresh`)

Jedno polecenie, które pobiera i przebudowuje dane z dwóch źródeł:

| Źródło | Co pobiera | Konektor |
|---|---|---|
| `interreg` | wykaz projektów Interreg 2021–2027 (plik XLSX ze strony `interreg.gov.pl/lista-projektow/`) | [`radar/sources/interreg.py`](../radar/sources/interreg.py) |
| `ncbr` | wyszukiwarka sukcesów beneficjentów NCBR (strona listy i strona szczegółów każdego projektu) | [`radar/sources/ncbr.py`](../radar/sources/ncbr.py) |

Po każdej przebudowie rekordy trafiają do bazy `data/radar.db` (moduł [`radar/store.py`](../radar/store.py)). Baza pamięta, kiedy projekt pojawił się pierwszy raz, kiedy zmienił się jego opis i czy zniknął ze źródła.

Skrypt pobiera tylko to, czego jeszcze nie ma albo co się zmieniło. Dzięki temu można go uruchamiać często, np. raz dziennie z harmonogramu.

## Wymagania

- Python ≥ 3.11, wyłącznie biblioteka standardowa (nic nie trzeba instalować).
- Uruchamiaj z katalogu głównego repozytorium. Ścieżki `data/...` są względne.
- Flaga `-X utf8` jest potrzebna na Windows, żeby polskie znaki w logach wyświetlały się poprawnie.

## Szybki start

```powershell
python -X utf8 -m radar.refresh
```

Pierwsze uruchomienie pobiera wszystko: Interreg w kilka sekund, NCBR w około 5 minut (ponad 300 stron, z 1 s przerwy między zapytaniami). Każde następne kończy się w sekundę, jeśli w źródłach nic się nie zmieniło.

## Przykłady użycia

Odśwież oba źródła, pobierając tylko nowości:

```powershell
python -X utf8 -m radar.refresh
```

Tylko jedno źródło:

```powershell
python -X utf8 -m radar.refresh --sources interreg
```

```powershell
python -X utf8 -m radar.refresh --sources ncbr
```

Sprawdź, co by się stało, bez zapisywania czegokolwiek (sieć jest używana tylko do odczytania strony Interreg):

```powershell
python -X utf8 -m radar.refresh --dry-run
```

Pobierz i przebuduj wszystko od nowa, ignorując zapisane pliki:

```powershell
python -X utf8 -m radar.refresh --force
```

Przebuduj wyniki z zapisanych plików, bez sieci (np. na prezentacji bez internetu):

```powershell
python -X utf8 -m radar.refresh --offline
```

Sprawdzaj listę NCBR częściej, np. co 2 godziny zamiast co 24:

```powershell
python -X utf8 -m radar.refresh --sources ncbr --max-age 2
```

Szybsze pobieranie NCBR (krótsza przerwa między zapytaniami, używaj z umiarem):

```powershell
python -X utf8 -m radar.refresh --sources ncbr --delay 0.3
```

## Opcje

| Opcja | Domyślnie | Opis |
|---|---|---|
| `--sources` | `interreg ncbr` | które źródła odświeżyć (jedno lub oba, oddzielone spacją) |
| `--raw-dir` | `data/raw` | gdzie trzymać surowe pliki (podkatalogi `interreg/`, `ncbr/`) |
| `--out-dir` | `data/normalized` | gdzie zapisać wyniki `*.jsonl` i `*.csv` |
| `--db` | `data/radar.db` | baza SQLite (albo zmienna `RADAR_DB`) |
| `--max-age` | `24` | NCBR: po ilu godzinach pobrać stronę listy ponownie |
| `--delay` | `1.0` | NCBR: sekundy przerwy między zapytaniami |
| `--force` | – | pobierz i przebuduj wszystko, ignorując cache |
| `--offline` | – | bez sieci, tylko z zapisanych plików (nie łączy się z `--force`) |
| `--dry-run` | – | pokaż, co by zrobiono, nic nie zapisuj |

## Co skrypt sprawdza, zanim coś pobierze

**Interreg**
1. Pobiera stronę z wykazem i odczytuje link do aktualnego pliku XLSX (w nazwie jest data publikacji, np. `..._20261116.xlsx`).
2. Jeśli ten sam plik jest już na dysku i jego suma SHA-256 zgadza się z zapisaną, **nie pobiera go ponownie**.
3. Jeśli pliku brakuje, jest uszkodzony albo na stronie pojawił się nowy, pobiera go. Pobrany plik musi być poprawnym XLSX (archiwum ZIP), inaczej zostaje poprzedni i źródło kończy się błędem.

**NCBR**
1. Strona listy jest pobierana ponownie dopiero, gdy zapisana jest starsza niż `--max-age` godzin.
2. Strony szczegółów już zapisane w `data/raw/ncbr/detail/` **nie są pobierane drugi raz**; pobierane są tylko karty nowych projektów.
3. Jeśli nowa strona listy nie zawiera żadnych kart (awaria albo zmiana strony), poprzednia lista zostaje.

**Oba źródła**
- Jeśli dane wejściowe (suma SHA-256 pliku XLSX lub strony listy) się nie zmieniły, a wynik istnieje i jest nienaruszony, przebudowa jest pomijana.
- Przed przebudową poprzedni wynik jest kopiowany do `*.prev.jsonl`.
- Jeśli liczba rekordów spadnie o ponad połowę, skrypt ostrzega i kończy się kodem 1 (zwykle oznacza to zmianę formatu źródła). Poprzednie dane są wtedy w `*.prev.jsonl`.
- Po przebudowie rekordy są zapisywane do bazy. Nowe dostają datę pierwszego pojawienia się, zmienione (inny `content_hash`) nową wersję, a te, których zabrakło w źródle, datę usunięcia. Nic nie jest kasowane.
- Błąd jednego źródła nie zatrzymuje drugiego.
- Plik `data/.refresh.lock` nie pozwala uruchomić dwóch odświeżeń naraz, także z różnych kontenerów Dockera. Blokada po zakończonym procesie na tym samym komputerze albo starsza niż 6 godzin jest przejmowana automatycznie.

## Jak czytać wynik

Przykład drugiego uruchomienia, gdy nic się nie zmieniło:

```text
[16:08:30] === interreg ===
[16:08:30] interreg: plik Wykaz_projektow_Interreg_2021-2027_art_49_CPR_20261116.xlsx już pobrany (SHA-256 zgodne), pomijam pobieranie
[16:08:30] interreg: dane wejściowe bez zmian, wynik aktualny, pomijam przebudowę
[16:08:30] interreg: OK {'download': 'skipped_already_have', 'rebuild': 'skipped_unchanged', 'records': 258} w 0.9 s
[16:08:30] === ncbr ===
[16:08:30] ncbr: lista pobrana 0.1 h temu (< 24.0 h), nie pobieram ponownie
[16:08:30] ncbr: lista bez zmian, wynik aktualny, pomijam przebudowę
[16:08:30] ncbr: OK {'list': 'skipped_fresh', 'rebuild': 'skipped_unchanged', 'records': 316} w 0.0 s
```

Wartości w podsumowaniu:

| Pole | Wartość | Znaczenie |
|---|---|---|
| `download` (Interreg) | `downloaded` | pobrano nowy plik XLSX |
| | `skipped_already_have` | plik już był na dysku |
| | `offline` / `would_download` | tryb `--offline` / `--dry-run` |
| `list` (NCBR) | `downloaded` | pobrano stronę listy |
| | `skipped_fresh` | lista młodsza niż `--max-age` |
| `rebuild` | `rebuilt` | wynik przebudowany |
| | `skipped_unchanged` | dane bez zmian, wynik pozostawiony |
| `records` | liczba | rekordów w wyniku |
| `added` / `changed` / `removed` | liczba | ile rekordów w bazie przybyło, zmieniło się, zniknęło ze źródła |
| `detail_pages_new` (NCBR) | liczba | ile nowych stron szczegółów pobrano |

## Kody wyjścia

| Kod | Znaczenie |
|---|---|
| `0` | wszystko w porządku |
| `1` | co najmniej jedno źródło zakończyło się błędem albo ostrzeżeniem o spadku liczby rekordów |
| `2` | błędne opcje wywołania |

## Pliki

```text
data/
├── raw/
│   ├── interreg/        list.html, plik XLSX, *.meta.json (URL, data pobrania, SHA-256)
│   └── ncbr/            list.html, detail/*.html, *.meta.json
├── normalized/
│   ├── interreg.jsonl   rekordy radar.record/v1 (+ interreg.csv, interreg.prev.jsonl)
│   └── ncbr.jsonl       rekordy radar.record/v1 (+ ncbr.csv, ncbr.prev.jsonl)
├── radar.db             baza SQLite: rekordy z historią, wyszukiwanie, karty, tabela refresh_runs
└── .refresh.lock        istnieje tylko w trakcie działania
```

`data/` jest w `.gitignore`, nic z tego nie trafia do repozytorium.

Podgląd zawartości bazy i wyszukiwanie:

```powershell
python -X utf8 -m radar.store stats
```

```powershell
python -X utf8 -m radar.store search "pompa ciepla"
```

Każde uruchomienie odświeżania jest zapisane w tabeli `refresh_runs`; ostatnie widać też w nagłówku przeglądarki (`python -X utf8 -m radar.gui`). Dawny plik `data/refresh_state.json` jest czytany tylko raz, przy pierwszym uruchomieniu z bazą.

## Uruchamianie automatyczne

Najprościej w Dockerze: kontener `scheduler` odświeża dane co 24 h, patrz [docker.md](docker.md).

### Harmonogram zadań Windows

Codziennie o 6:00 (`schtasks` uruchamia polecenie w katalogu systemowym, dlatego najpierw `cd /d` do repozytorium; podmień ścieżkę na swoją):

```powershell
schtasks /Create /TN "Radar - odswiezanie danych" /SC DAILY /ST 06:00 /TR "cmd /c cd /d C:\sciezka\do\repo && python -X utf8 -m radar.refresh >> data\refresh.log 2>&1"
```

Na Linuksie / macOS wpis w `crontab -e`:

```text
0 6 * * * cd /sciezka/do/repo && python3 -X utf8 -m radar.refresh >> data/refresh.log 2>&1
```

## Rozwiązywanie problemów

| Komunikat | Co zrobić |
|---|---|
| `odświeżanie już trwa (pid ...)` | poczekaj, aż poprzednie się skończy; jeśli żadne nie działa, usuń `data/.refresh.lock` |
| `brak poprawnego zapisanego pliku` / `brak zapisanej strony listy` przy `--offline` | uruchom raz bez `--offline`, żeby pobrać dane |
| `nie ma linku do pliku .xlsx` / `nie jest plikiem XLSX` | strona Interreg zmieniła układ; poprzednie dane zostają, trzeba poprawić konektor |
| `UWAGA: liczba rekordów spadła z X do Y` | sprawdź źródło; poprzedni wynik jest w `*.prev.jsonl` |
| `FetchError` | brak sieci albo serwer źródła nie odpowiada; spróbuj później, drugie źródło i tak zostało odświeżone |
