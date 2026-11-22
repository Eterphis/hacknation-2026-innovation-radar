"""An openly transferred way of working (school, municipality, NGO) is not valued like a technology licence."""

from types import SimpleNamespace

from radar.business import BUSINESS_VERSION, business_case


def _rec(innovation_type, cost="sredni", amounts=None):
    return SimpleNamespace(innovation_type=innovation_type, cost_level=cost, amounts=amounts or {}, sector="P_edukacja",
                           voivodeship="podkarpackie", title="t", abstract="a", institution_type="szkola", tech_area=None,
                           source_id="x", extra={})


def _card():
    return SimpleNamespace(maturity="business_ready")


def test_model_transfer_has_no_licence_and_shows_adopters_savings():
    bc = business_case(_rec("edukacyjna"), _card())
    v = bc["valuation"]
    assert bc["version"] == BUSINESS_VERSION and v["open_model"] is True
    assert v["licence_or_spinoff_pln"] == 0 and v["royalty_3y_pln"] == 0
    assert v["headline_pln"] == v["public_value_3y_pln"] > 0 and v["headline"] == "oszczędność odbiorców w 3 lata"
    assert bc["deploy_cost_pln"] <= 150_000  # a copied programme, not a 600k technology rollout


def test_technology_keeps_its_licence_value():
    v = business_case(_rec("technologiczna"), _card())["valuation"]
    assert v["open_model"] is False and v["licence_or_spinoff_pln"] > 0 and v["headline"] == "wartość licencji / spin-off"


def test_model_copy_is_a_tenth_of_the_original_budget():
    bc = business_case(_rec("organizacyjna", amounts={"budzet": 1_000_000}), _card())
    assert bc["deploy_cost_pln"] == 100_000
