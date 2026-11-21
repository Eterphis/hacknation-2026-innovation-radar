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
IDEA = ("System wczesnego wykrywania wycieków w sieci wodociągowej gminy",
        "Politechnika Rzeszowska opracowała system czujników akustycznych i aplikację, która na podstawie modelu "
        "uczenia maszynowego wykrywa wycieki w sieci wodociągowej w ciągu kilku godzin. Prototyp przetestowano w "
        "pilotażu w gminie Krasne; rozwiązanie zmniejszyło straty wody o 18% i jest gotowe do wdrożenia w innych gminach.")


def basal(title, abstract):
    return classify(title=title, abstract=abstract, affiliations=["Gmina Krasne", "Politechnika Rzeszowska"],
                    region="podkarpackie", kind="project")


@pytest.mark.parametrize("name", sorted(INFRA))
def test_infrastructure_is_rejected_before_llm(name):
    title, abstract = INFRA[name]
    b = basal(title, abstract)
    assert b["decision"] == "reject", b["reject_reasons"]
    assert any(r.startswith("inwestycja infrastrukturalna") for r in b["reject_reasons"]), b["reject_reasons"]
    assert T.is_infrastructure(title, abstract)


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
