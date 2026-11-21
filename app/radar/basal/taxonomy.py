"""Basal label sets. Each label has: Polish name, keyword patterns (on folded text: lowercase, no Polish
letters) and a prototype description used for embedding similarity. Patterns are word-stem regexes.

Editing a label here changes classification everywhere; every decision stores which patterns matched.
"""

from __future__ import annotations

import re

from radar.basal.embed import fold

# --------------------------------------------------------------------------- sector (PKD 2007 sections)
SECTORS: dict[str, dict] = {
    "A_rolnictwo": {"pl": "Rolnictwo, leśnictwo, żywność",
                    "kw": [r"rolni", r"upraw", r"hodowl", r"lesn", r"zywnos", r"mlecz", r"agro", r"gleb", r"nawoz", r"przetworstw\w* spozywcz"],
                    "proto": "rolnictwo uprawy hodowla zwierząt gospodarstwa rolne przetwórstwo żywności leśnictwo agrotechnika"},
    "C_przemysl": {"pl": "Przetwórstwo przemysłowe",
                   "kw": [r"przemysl", r"produkcj", r"zaklad\w* produkc", r"obrobk", r"maszyn", r"kompozyt", r"material", r"odlew", r"spawan", r"fabryk", r"lotnicz", r"motoryzac", r"samochod"],
                   "proto": "przemysł produkcja zakłady produkcyjne maszyny materiały kompozyty obróbka fabryka lotnictwo motoryzacja"},
    "D_energetyka": {"pl": "Energetyka",
                     "kw": [r"energ", r"wodor", r"fotowolt", r"elektrolizer", r"magazyn\w* energi", r"oze\b", r"cieplo", r"cieplown", r"turbin", r"elektrown"],
                     "proto": "energetyka odnawialne źródła energii wodór fotowoltaika magazyny energii ciepłownictwo sieci energetyczne"},
    "E_srodowisko": {"pl": "Woda, ścieki, odpady, środowisko",
                     "kw": [r"odpad", r"recykl", r"sciek", r"wod\w* pitn", r"wodociag", r"srodowisk", r"emisj", r"powietrz", r"smog", r"klimat"],
                     "proto": "gospodarka odpadami recykling oczyszczanie ścieków woda pitna ochrona środowiska jakość powietrza klimat"},
    "F_budownictwo": {"pl": "Budownictwo",
                      "kw": [r"budown", r"budyn", r"termomoderniz", r"konstrukc", r"beton", r"infrastruktur\w* drogow", r"remont"],
                      "proto": "budownictwo budynki konstrukcje termomodernizacja beton infrastruktura budowlana"},
    "H_transport": {"pl": "Transport i logistyka",
                    "kw": [r"transport", r"logisty", r"dowoz", r"komunikac\w* (?:publiczn|zbiorow)", r"kolej", r"autobus", r"mobilnos", r"przewoz"],
                    "proto": "transport publiczny logistyka przewozy mobilność dowóz komunikacja kolej autobusy"},
    "J_ict": {"pl": "Informacja i komunikacja (ICT)",
              "kw": [r"oprogramow", r"aplikac", r"platform\w* (?:cyfrow|internet|onlin)", r"system\w* informatycz", r"\bonline\b", r"cyfrow", r"internet",
                     r"(?:analiz|baz|przetwarzani|zbior)\w* danych|danych osobowych", r"chmur", r"cyberbezpiecz", r"sztuczn\w* inteligenc", r"\bai\b"],
              "proto": "oprogramowanie aplikacje platformy cyfrowe systemy informatyczne dane internet sztuczna inteligencja cyberbezpieczeństwo"},
    "M_nauka": {"pl": "Działalność naukowa i techniczna",
                "kw": [r"badan", r"laborator", r"naukow", r"metod\w* (?:badaw|pomiar)", r"pomiar", r"analiz\w* (?:chemicz|laborator)", r"b\+r"],
                "proto": "badania naukowe laboratorium metody pomiarowe analizy badania i rozwój nauka techniczna"},
    "O_administracja": {"pl": "Administracja publiczna",
                        "kw": [r"urzed", r"gmin", r"samorzad", r"administrac", r"e-?uslug", r"mieszkan", r"powiat", r"marszalk", r"procedur"],
                        "proto": "administracja publiczna urząd gmina samorząd e-usługi dla mieszkańców procedury urzędowe"},
    "P_edukacja": {"pl": "Edukacja",
                   "kw": [r"szkol", r"uczni", r"nauczyc", r"eduka", r"dydakty", r"przedszkol", r"student", r"kszta?lcen", r"lekcj"],
                   "proto": "edukacja szkoła uczniowie nauczyciele dydaktyka kształcenie przedszkole studenci lekcje"},
    "Q_zdrowie": {"pl": "Opieka zdrowotna i pomoc społeczna",
                  "kw": [r"zdrow", r"medycz", r"pacjent", r"szpital", r"rehabilit", r"senior", r"opiek", r"terapi", r"diagnost", r"pomoc\w* spoleczn", r"niepelnospraw"],
                  "proto": "ochrona zdrowia medycyna pacjenci szpital rehabilitacja opieka nad seniorami pomoc społeczna diagnostyka terapia"},
    "R_kultura": {"pl": "Kultura, sport, turystyka",
                  "kw": [r"kultur", r"muze", r"sport", r"turyst", r"dziedzictw", r"bibliotek", r"rekreac"],
                  "proto": "kultura muzea biblioteki dziedzictwo sport rekreacja turystyka"},
}

# --------------------------------------------------------------------------- technology area
TECH_AREAS: dict[str, dict] = {
    "ai_dane": {"pl": "AI i analiza danych", "kw": [r"sztuczn\w* inteligenc", r"\bai\b", r"uczeni\w* maszyn", r"sieci neuron", r"analiz\w* (?:obrazu|danych)", r"rozpoznawan", r"predykc", r"algorytm"],
                "proto": "sztuczna inteligencja uczenie maszynowe analiza obrazu analiza danych algorytmy predykcja"},
    "iot_czujniki": {"pl": "IoT i czujniki", "kw": [r"czujnik", r"sensor", r"\biot\b", r"internet rzeczy", r"monitoring", r"telemetri", r"pomiar"],
                     "proto": "czujniki sensory internet rzeczy monitoring telemetria pomiary w czasie rzeczywistym"},
    "energia_wodor": {"pl": "Energia i wodór", "kw": [r"wodor", r"elektrolizer", r"ogniw", r"fotowolt", r"magazyn\w* energi", r"bateri", r"akumulator", r"energ\w* odnawial"],
                      "proto": "wodór elektrolizery ogniwa paliwowe fotowoltaika magazyny energii baterie odnawialne źródła"},
    "materialy": {"pl": "Materiały i kompozyty", "kw": [r"kompozyt", r"material", r"polimer", r"powlok", r"stop\w* metal", r"nanomateri", r"termograf", r"nieniszcz"],
                  "proto": "materiały kompozyty polimery powłoki stopy metali badania nieniszczące"},
    "lotnictwo_kosmos": {"pl": "Lotnictwo i kosmos", "kw": [r"lotnic", r"samolot", r"dron", r"bezzalogow", r"kosmicz", r"satelit", r"awiony"],
                         "proto": "lotnictwo samoloty drony bezzałogowe statki technologie kosmiczne satelity"},
    "motoryzacja": {"pl": "Motoryzacja i e-mobilność", "kw": [r"motoryzac", r"samochod", r"pojazd", r"elektromobil", r"silnik", r"ladowar"],
                    "proto": "motoryzacja samochody pojazdy elektromobilność silniki ładowarki"},
    "biotech_medtech": {"pl": "Biotechnologia i medtech", "kw": [r"biotechnolog", r"medycz", r"diagnost", r"lek\b|lekow", r"terapi", r"protez", r"wyrob\w* medycz", r"rehabilit"],
                        "proto": "biotechnologia wyroby medyczne diagnostyka terapie leki protezy rehabilitacja"},
    "agro_zywnosc": {"pl": "Agrotech i żywność", "kw": [r"rolnict\w* precyz", r"agro", r"zywnos", r"upraw", r"nawoz", r"pasz"],
                     "proto": "rolnictwo precyzyjne agrotechnika żywność uprawy nawozy pasze"},
    "srodowisko_tech": {"pl": "Technologie środowiskowe", "kw": [r"recykl", r"odpad", r"oczyszcz", r"sciek", r"emisj", r"filtr", r"gospodark\w* obieg"],
                        "proto": "recykling odpady oczyszczanie ścieków redukcja emisji filtry gospodarka obiegu zamkniętego"},
    "budownictwo_tech": {"pl": "Technologie budowlane", "kw": [r"budown", r"beton", r"konstrukc", r"termomoderniz", r"prefabryk"],
                         "proto": "technologie budowlane beton konstrukcje termomodernizacja prefabrykacja"},
    "oprogramowanie_euslugi": {"pl": "Oprogramowanie i e-usługi", "kw": [r"aplikac", r"oprogramow", r"platform", r"system\w* (?:informatycz|zapisow|rezerwac)", r"e-?uslug", r"\bonline\b", r"portal"],
                               "proto": "aplikacja oprogramowanie platforma internetowa system informatyczny e-usługi portal online"},
    "robotyka_automatyka": {"pl": "Robotyka i automatyka", "kw": [r"robot", r"automatyz", r"automatyk", r"sterown", r"manipulator", r"linia produkcyjn"],
                            "proto": "robotyka automatyzacja automatyka sterowniki manipulatory linie produkcyjne"},
    "metody_nietech": {"pl": "Metody nietechnologiczne (organizacja, edukacja, usługi)", "kw": [r"model\w* dzialan", r"program\w* (?:mentor|eduk|wsparc)", r"mentoring", r"koordynator", r"harmonogram", r"wspolprac", r"procedur", r"warsztat", r"zajec"],
                       "proto": "model działania program mentoringu koordynacja współpraca procedura organizacyjna zajęcia warsztaty usługa społeczna"},
}

# --------------------------------------------------------------------------- innovation type (shared with extract.py)
INNOVATION_TYPES: dict[str, dict] = {
    "technologiczna": {"pl": "technologiczna", "kw": [r"technolog", r"urzadzen", r"prototyp", r"patent", r"metod\w* (?:pomiar|badaw|wytwarz)", r"material", r"czujnik", r"ogniw"],
                       "proto": "nowa technologia urządzenie prototyp patent metoda wytwarzania"},
    "organizacyjna": {"pl": "organizacyjna", "kw": [r"organizac", r"model\w* dzialan", r"koordynator", r"zarzadzan", r"wspolprac\w* (?:miedzy|instytuc)"],
                      "proto": "nowy model organizacji pracy koordynacja zarządzanie współpraca instytucji"},
    "edukacyjna": {"pl": "edukacyjna", "kw": [r"eduka", r"uczni", r"nauczyc", r"szkol", r"dydakt", r"mentoring", r"lekcj", r"kszta?lcen"],
                   "proto": "nowa metoda edukacyjna program dla uczniów nauczyciele dydaktyka"},
    "spoleczna": {"pl": "społeczna", "kw": [r"spoleczn", r"senior", r"mieszkan", r"wyklucz", r"niepelnospraw", r"wolontar", r"ngo|organizacj\w* pozarzad"],
                  "proto": "innowacja społeczna wsparcie seniorów mieszkańców osób wykluczonych organizacje pozarządowe"},
    "procesowa": {"pl": "procesowa", "kw": [r"proces", r"procedur", r"usprawni", r"skraca", r"automatyz\w* proces", r"optymaliz"],
                  "proto": "usprawnienie procesu procedury optymalizacja skrócenie czasu obsługi"},
    "uslugowa": {"pl": "usługowa", "kw": [r"uslug", r"wypozycz", r"na wezwanie", r"zamawian", r"obslug\w* klient", r"e-?uslug"],
                 "proto": "nowa usługa publiczna wypożyczalnia usługa na wezwanie obsługa mieszkańców"},
}

# --------------------------------------------------------------------------- institution type
INSTITUTION_TYPES: dict[str, dict] = {
    "szkola": {"pl": "szkoła", "kw": [r"szkol\w* (?:podstaw|sredni|zawod)", r"liceum", r"technikum", r"przedszkol", r"zespol szkol"]},
    "uczelnia": {"pl": "uczelnia", "kw": [r"politechnik", r"uniwersytet", r"akademi", r"uczelni", r"wydzial", r"katedr", r"szkol\w* wyzsz",
                                         r"\buniversit", r"\bhochschule", r"\buniverzit", r"\bvysok\w* skol"]},
    "instytut": {"pl": "instytut badawczy / PAN", "kw": [r"instytut", r"\bpan\b|polsk\w* akademi\w* nauk", r"siec\w* badawcz\w* lukasiewicz|lukasiewicz",
                                                        r"\binstitut", r"research cent(?:re|er)"]},
    "jst": {"pl": "JST (gmina, powiat, województwo)", "kw": [r"\bgmin", r"\bmiasto\b|urzad miast", r"powiat", r"marszalk",
                                                            r"wojewodztw\w* (?:podkarp|samorz|\w+skie)", r"samorzad", r"centrum uslug spoleczn", r"ops\b|osrodek pomocy",
                                                            r"\bcommune\b", r"\bmunicipalit", r"\bvoivodeship\b", r"\bcity council", r"\bstadt\b", r"\bgemeinde",
                                                            r"\bobec\b", r"\bmesto\b", r"euroregion", r"zwiazek (?:gmin|powiat|miast)",
                                                            r"ugrupowanie wspolpracy terytorialnej|\beuwt\b"]},
    "inna_publiczna": {"pl": "inna instytucja publiczna", "kw": [r"szpital", r"biblioteka", r"muzeum", r"agencja", r"centrum (?:innowac|kultury)", r"urzad (?!miast)",
                                                                 r"\bhospital", r"public health care|\bzoz\b|zaklad opieki zdrowotnej",
                                                                 r"komend\w* (?:wojewodzk|powiatow|miejsk|glown)", r"\bpolicj", r"straz\w* (?:pozarn|granicz)",
                                                                 r"fire service|border guard", r"\bmuseum", r"centrum kliniczn",
                                                                 r"port authority|urzad morsk", r"doradztwa rolniczego|advisory cent"]},
    "firma": {"pl": "firma prywatna", "kw": [r"sp\.? ?z ?o\.? ?o", r"\bs\.a\.?(?=[\s,;)]|$)", r"spolka", r"\bsp\. k\b", r"\bsp\. ?j\b", r"przedsiebiorstw",
                                             r"\bgmbh\b", r"\bb\.v\.", r"\ba\.s\.(?=[\s,;)]|$)"]},
}
# Associations and foundations: not a public institution and not a company -> the operator decides (hold).
NGO_KW = [r"fundacj", r"stowarzysz", r"\bassociation\b", r"\bfoundation\b", r"\be\.v\.", r"\bverein\b", r"\bzdruzenie\b"]
INSTITUTION_FIELD_MAP = {  # values typed in the submission form
    "szkoła": "szkola", "szkola": "szkola", "uczelnia": "uczelnia", "instytut": "instytut", "jst": "jst", "JST": "jst",
    "gmina": "jst", "inna instytucja publiczna": "inna_publiczna", "firma": "firma",
}

# --------------------------------------------------------------------------- maturity signals
MATURITY_KW: dict[str, list[str]] = {
    "market_ready": [r"wdrozon\w* w (?:kilku|wielu|innych)", r"stosowan\w* (?:przez|w) (?:inn|wiel)", r"w sprzedazy", r"komercyjn\w* dostep"],
    "business_ready": [r"wdrozon", r"wdrozeni", r"wdrozyl", r"uruchomil", r"dzial\w* (?:od|przez)", r"spin-?off", r"licencj", r"inwestycj"],
    "tech_ready": [r"prototyp", r"pilotaz", r"pilotazow", r"demonstrator", r"patent", r"zgloszeni\w* patent", r"przetestowan", r"sprawdzon\w* w"],
    "exploring": [r"badan", r"koncepcj", r"analiz", r"model\w* teoretycz", r"artykul"],
}

# --------------------------------------------------------------------------- cost
COST_LEVELS = ["niski", "sredni", "wysoki", "bardzo_wysoki"]
COST_PL = {"niski": "niski (< 100 tys. zł)", "sredni": "średni (100 tys. – 2 mln zł)",
           "wysoki": "wysoki (2–20 mln zł)", "bardzo_wysoki": "bardzo wysoki (> 20 mln zł)"}
COST_KW = {
    "niski": [r"bez dodatkowych kosztow", r"niskim kosztem|niski koszt", r"wolontar", r"bezplatn", r"istniejac\w* zasob"],
    "wysoki": [r"laborator", r"infrastruktur", r"linia produkcyjn", r"budow\w* (?:obiekt|zakladu)", r"aparatur"],
    "bardzo_wysoki": [r"elektrown", r"zaklad\w* produkcyjn\w* od podstaw", r"centrum badawcz"],
}

# --------------------------------------------------------------------------- gate (reject / hold)
NEGATIVE = [r"oferta pracy|oferty pracy|rekrutacj", r"przetarg|zapytanie ofertowe", r"polityka prywatnosci", r"regulamin",
            r"deklaracja dostepnosci", r"wyniki wyborow|sesja rady", r"konkurs na stanowisko"]
SPAM = [r"kup teraz", r"promocj\w* -?\d+ ?%", r"kasyno|casino", r"zarabiaj", r"kliknij tutaj", r"viagra", r"kredyt\w* bez"]
OFFENSIVE = [r"\bkurw", r"\bchuj", r"\bpierdol", r"\bjeb\w*", r"\bspierdal"]
# Large public works are investments, not transferable innovations: roads, pipelines, railway lines would crowd out
# every queue and money ranking. Checked on the title and the first 300 characters of the description (folded).
INFRASTRUCTURE = re.compile(
    r"\b(budow\w* (?:drogi|odcink|obwodnic|gazociag|linii|mostu|wezla|trasy|tunelu)|droga ekspresow|autostrad|obwodnic|gazociag|"
    r"modernizacj\w* linii kolejow|linii kolejow|rozbudow\w* (?:drogi|portu|lotniska)|przebudow\w* drogi|sieci\w* przesyl|terminal\w* (?:lng|kontener))")


def infrastructure_match(title: str | None, abstract: str | None = None) -> str | None:
    """The phrase that marks a record as an infrastructure investment, or None."""
    m = INFRASTRUCTURE.search(fold(f"{title or ''} {(abstract or '')[:300]}"))
    return m.group(0) if m else None


def is_infrastructure(title: str | None, abstract: str | None = None) -> bool:
    return infrastructure_match(title, abstract) is not None


SIGNAL = [r"opracow", r"wdroz", r"prototyp", r"metod", r"system", r"program", r"pilota", r"model", r"rozwiaz", r"aplikac",
          r"narzedz", r"technolog", r"innowac", r"uslug", r"usprawni", r"develop", r"method", r"prototype", r"platform", r"urzadz"]

VOIVODESHIPS = {
    "dolnoslaskie": "dolnośląskie", "kujawsko-pomorskie": "kujawsko-pomorskie", "lubelskie": "lubelskie",
    "lubuskie": "lubuskie", "lodzkie": "łódzkie", "malopolskie": "małopolskie", "mazowieckie": "mazowieckie",
    "opolskie": "opolskie", "podkarpackie": "podkarpackie", "podlaskie": "podlaskie", "pomorskie": "pomorskie",
    "slaskie": "śląskie", "swietokrzyskie": "świętokrzyskie", "warminsko-mazurskie": "warmińsko-mazurskie",
    "wielkopolskie": "wielkopolskie", "zachodniopomorskie": "zachodniopomorskie",
}
# Cities and well-known institution names -> voivodeship (folded). Extend as data grows.
CITY_VOIV = {
    "rzeszow": "podkarpackie", "krosn": "podkarpackie", "przemysl": "podkarpackie", "mielec": "podkarpackie",
    "tarnobrzeg": "podkarpackie", "sanok": "podkarpackie", "jaslo": "podkarpackie", "dukl": "podkarpackie", "debic": "podkarpackie",
    "krakow": "małopolskie", "tarnow": "małopolskie", "nowy sacz": "małopolskie",
    "warszaw": "mazowieckie", "radom": "mazowieckie", "plock": "mazowieckie",
    "wroclaw": "dolnośląskie", "legnic": "dolnośląskie", "poznan": "wielkopolskie", "kalisz": "wielkopolskie",
    "gdansk": "pomorskie", "gdyni": "pomorskie", "slupsk": "pomorskie", "lodz": "łódzkie", "katowic": "śląskie",
    "gliwic": "śląskie", "czestochow": "śląskie", "bielsk": "śląskie", "lublin": "lubelskie", "zamosc": "lubelskie",
    "bialystok": "podlaskie", "olsztyn": "warmińsko-mazurskie", "elblag": "warmińsko-mazurskie", "szczecin": "zachodniopomorskie",
    "koszalin": "zachodniopomorskie", "bydgoszcz": "kujawsko-pomorskie", "torun": "kujawsko-pomorskie", "kielc": "świętokrzyskie",
    "opol": "opolskie", "zielon\\w* gor": "lubuskie", "gorzow": "lubuskie",
}

# Display names for CITY_VOIV keys (location plates in the UI)
CITY_NAME = {
    "rzeszow": "Rzeszów", "krosn": "Krosno", "przemysl": "Przemyśl", "mielec": "Mielec", "tarnobrzeg": "Tarnobrzeg",
    "sanok": "Sanok", "jaslo": "Jasło", "dukl": "Dukla", "debic": "Dębica", "krakow": "Kraków", "tarnow": "Tarnów",
    "nowy sacz": "Nowy Sącz", "warszaw": "Warszawa", "radom": "Radom", "plock": "Płock", "wroclaw": "Wrocław",
    "legnic": "Legnica", "poznan": "Poznań", "kalisz": "Kalisz", "gdansk": "Gdańsk", "gdyni": "Gdynia", "slupsk": "Słupsk",
    "lodz": "Łódź", "katowic": "Katowice", "gliwic": "Gliwice", "czestochow": "Częstochowa", "bielsk": "Bielsko-Biała",
    "lublin": "Lublin", "zamosc": "Zamość", "bialystok": "Białystok", "olsztyn": "Olsztyn", "elblag": "Elbląg",
    "szczecin": "Szczecin", "koszalin": "Koszalin", "bydgoszcz": "Bydgoszcz", "torun": "Toruń", "kielc": "Kielce",
    "opol": "Opole", r"zielon\w* gor": "Zielona Góra", "gorzow": "Gorzów Wielkopolski",
}
COST_RANGE = {"niski": "do 100 tys. zł", "sredni": "100 tys. – 2 mln zł", "wysoki": "2–20 mln zł", "bardzo_wysoki": "powyżej 20 mln zł"}
