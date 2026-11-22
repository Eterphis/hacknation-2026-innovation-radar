"""Basal rejects infrastructure investments (roads, gas pipelines, railway lines) before the LLM queue, with the
reason "inwestycja infrastrukturalna"; an innovative idea from a public institution still passes. The audience
views (business.is_infrastructure) use the same rule."""

from types import SimpleNamespace

import pytest

from radar import business
from radar.basal import taxonomy as T
from radar.basal.classifier import classify

TAIL = (" Projekt realizuje samorząd we współpracy z wykonawcą wyłonionym w przetargu. Inwestycja obejmuje "
        "prace przygotowawcze, roboty budowlane, nadzór inwestorski oraz promocję projektu, a jej celem jest poprawa "
        "dostępności komunikacyjnej regionu i bezpieczeństwa mieszkańców.")
INFRA = {
    "droga": ("Budowa drogi ekspresowej S19 na odcinku Rzeszów Południe – Babica",
              "Przedmiotem projektu jest budowa drogi ekspresowej S19 o długości 8 km wraz z węzłami." + TAIL),
    "gazociąg": ("Gazociąg Hermanowice – Strachocina",
                 "Projekt obejmuje budowę gazociągu wysokiego ciśnienia DN 1000 wraz z infrastrukturą towarzyszącą." + TAIL),
    "kolej": ("Prace na linii kolejowej nr 91 Kraków – Medyka",
              "Modernizacja linii kolejowej nr 91 na odcinku Rzeszów – Przeworsk, w tym przebudowa peronów." + TAIL),
}
# EU-funded works: the boilerplate hits the loose SIGNAL words (program, system, wdrożenie, technolog), still rejected.
INFRA_EU = {
    "terminal": ("Rozbudowa terminala LNG w Świnoujściu",
                 "Projekt w ramach Programu Operacyjnego Infrastruktura i Środowisko 2014-2020 obejmuje budowę trzeciego "
                 "zbiornika i infrastruktury technologicznej oraz zwiększenie zdolności regazyfikacji." + TAIL),
    "ertms": ("Modernizacja linii kolejowej E30 na odcinku Kraków – Rzeszów",
              "Program Operacyjny Infrastruktura i Środowisko. Projekt obejmuje modernizację torów, wdrożenie systemu "
              "ERTMS/ETCS oraz przebudowę stacji i przystanków." + TAIL),
}
# Innovations about infrastructure: the rule matches, but the text describes building a solution, so no reject.
INNOVATION_ON_INFRA = {
    "mosty": ("System monitorowania stanu mostów na autostradach z użyciem czujników IoT",
              "Politechnika Rzeszowska opracowała sieć czujników drgań i aplikację, która na podstawie modelu uczenia "
              "maszynowego wykrywa uszkodzenia konstrukcji mostów. Prototyp przetestowano w pilotażu z zarządcą drogi; "
              "rozwiązanie skraca przeglądy i jest gotowe do wdrożenia przez inne gminy i zarządców dróg."),
    "gazociąg": ("Cyfrowy bliźniak gazociągu do predykcji awarii",
                 "Uczelnia we współpracy z gminą opracowała model i narzędzie, które na podstawie danych z czujników "
                 "ciśnienia prognozuje awarie sieci. Pilotaż w gminie Krasne pokazał wykrycie usterek z wyprzedzeniem "
                 "kilku dni; metodę można przenieść do innych operatorów sieci gazowych i wodociągowych."),
    "kolej": ("Nowa metoda diagnostyki linii kolejowych z użyciem dronów",
              "Politechnika opracowała metodę i aplikację do automatycznej oceny stanu torów na zdjęciach z dronów. "
              "Algorytm rozpoznaje pęknięcia szyn i podkładów; prototyp przetestowano w pilotażu na liniach lokalnych, "
              "a samorząd województwa planuje wdrożenie na kolejnych odcinkach."),
}
IDEA = ("System wczesnego wykrywania wycieków w sieci wodociągowej gminy",
        "Politechnika Rzeszowska opracowała system czujników akustycznych i aplikację, która na podstawie modelu "
        "uczenia maszynowego wykrywa wycieki w sieci wodociągowej w ciągu kilku godzin. Prototyp przetestowano w "
        "pilotażu w gminie Krasne; rozwiązanie zmniejszyło straty wody o 18% i jest gotowe do wdrożenia w innych gminach.")


def basal(title, abstract):
    return classify(title=title, abstract=abstract, affiliations=["Gmina Krasne", "Politechnika Rzeszowska"],
                    region="podkarpackie", kind="project")


@pytest.mark.parametrize("title,abstract", [*INFRA.values(), *INFRA_EU.values()], ids=[*INFRA, *INFRA_EU])
def test_infrastructure_is_rejected_before_llm(title, abstract):
    b = basal(title, abstract)
    assert b["decision"] == "reject", b["reject_reasons"]
    assert any(r.startswith("inwestycja infrastrukturalna") for r in b["reject_reasons"]), b["reject_reasons"]
    assert T.is_infrastructure(title, abstract)


@pytest.mark.parametrize("name", sorted(INNOVATION_ON_INFRA))
def test_innovation_about_infrastructure_is_not_rejected(name):
    title, abstract = INNOVATION_ON_INFRA[name]
    assert T.is_infrastructure(title, abstract), "the case must hit the rule, or it tests nothing"
    b = basal(title, abstract)
    assert not any(r.startswith("inwestycja infrastrukturalna") for r in b["reject_reasons"]), b["reject_reasons"]
    assert b["decision"] != "reject", b["reject_reasons"]
    assert any(r.startswith("dotyczy infrastruktury") for r in b["hold_reasons"]), b["hold_reasons"]


def test_version_marks_the_new_rule():
    b = basal(*IDEA)
    assert b["version"] == "basal/v2"


def test_innovative_idea_passes():
    b = basal(*IDEA)
    assert not any("infrastruktur" in r for r in b["reject_reasons"])
    assert b["decision"] != "reject", b["reject_reasons"]
    assert not T.is_infrastructure(*IDEA)


def test_audience_views_use_the_same_rule():
    for title, abstract in [*INFRA.values(), IDEA]:
        rec = SimpleNamespace(title=title, abstract=abstract)
        assert business.is_infrastructure(rec) == T.is_infrastructure(title, abstract)
    assert not hasattr(business, "INFRA"), "the rule lives in basal/taxonomy.py only"
