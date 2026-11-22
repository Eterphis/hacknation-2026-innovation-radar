"""Issue #30 tasks 4 and 7: anonymous demand counters, demand vs supply map, trending (pure functions)."""

import json
from datetime import date, timedelta

from radar import demand as D

DAY = date(2026, 11, 22)


def test_profile_rows_keep_only_vocabulary_values():
    rows = D.profile_rows({"role": "samorzady", "voivodeship": "Podkarpackie", "sectors": ["E_srodowisko", "Q_zdrowie", "x"],
                           "budget": "sredni", "email": "a@b.pl", "name": "Jan", "voter": "abc"}, DAY)
    assert len(rows) == 2 and {r["sector"] for r in rows} == {"E_srodowisko", "Q_zdrowie"}
    assert all(set(r) == {"day", "role", "voivodeship", "sector", "budget", "n"} for r in rows)
    assert rows[0]["voivodeship"] == "podkarpackie" and "a@b.pl" not in json.dumps(rows)
    assert D.profile_rows({"role": "hacker"}, DAY) == []
    assert D.profile_rows({"role": "szkoly", "sectors": "P_edukacja", "budget": "milion"}, DAY)[0]["budget"] is None
    assert D.profile_rows({"role": "szkoly"}, DAY)[0]["sector"] is None


def test_signal_row_and_merge():
    assert D.signal_row(5, "save", "śląskie", DAY) == {"day": "2026-11-22", "card_id": 5, "kind": "save", "voivodeship": "śląskie", "n": 1}
    assert D.signal_row(5, "delete") is None and D.signal_row(-1, "save") is None
    merged = D.merge([D.signal_row(5, "save", None, DAY)] * 3, ("day", "card_id", "kind", "voivodeship"))
    assert merged == [{"day": "2026-11-22", "card_id": 5, "kind": "save", "voivodeship": None, "n": 3}]


def test_demand_map_counts_demand_vs_supply_and_suppresses_small_cells():
    profiles = [{"role": "samorzady", "voivodeship": "podkarpackie", "sector": "E_srodowisko", "n": 4},
                {"role": "samorzady", "voivodeship": "lubelskie", "sector": "E_srodowisko", "n": 2},  # < MIN_CELL
                {"role": "inwestorzy", "voivodeship": "podkarpackie", "sector": "J_ict", "n": 9}]
    signals = [{"card_id": 1, "kind": "save", "sector": "E_srodowisko", "card_voivodeship": "podkarpackie", "n": 3}]
    likes = [{"card_id": 1, "sector": "E_srodowisko", "card_voivodeship": "podkarpackie", "n": 5}]
    supply = [{"voivodeship": "podkarpackie", "sector": "E_srodowisko", "n": 2},
              {"voivodeship": "mazowieckie", "sector": "E_srodowisko", "n": 40}]
    m = D.demand_map(profiles, signals, likes, supply, sector="E_srodowisko")
    by = {r["voivodeship"]: r for r in m["regions"]}
    assert len(by) == 16 and m["regions"][0]["voivodeship"] == "podkarpackie"
    pk = by["podkarpackie"]
    assert pk["demand"] == {"profiles": 4, "profiles_suppressed": False, "saves": 3, "deals": 0, "compares": 0, "likes": 5,
                            "index": 3 * 4 + 2 * 3 + 5}
    assert pk["supply"] == 2 and pk["label"] == "niedobór podaży"
    assert by["lubelskie"]["demand"]["profiles"] == 0 and by["lubelskie"]["demand"]["profiles_suppressed"]
    assert by["mazowieckie"]["label"] == "nadwyżka podaży" and by["opolskie"]["label"] == "brak danych"
    assert D.demand_map(profiles, [], [], [], sector=None)["totals"]["demand_index"] == 3 * (4 + 9)


def test_trending_decays_and_filters_region():
    rows = [
        {"day": DAY.isoformat(), "card_id": 1, "kind": "save", "voivodeship": "podkarpackie", "n": 2},
        {"day": (DAY - timedelta(days=14)).isoformat(), "card_id": 2, "kind": "deal", "voivodeship": "podkarpackie", "n": 3},
        {"day": (DAY - timedelta(days=1)).isoformat(), "card_id": 3, "kind": "like", "card_voivodeship": "mazowieckie", "n": 10},
        {"day": (DAY - timedelta(days=40)).isoformat(), "card_id": 4, "kind": "deal", "voivodeship": "podkarpackie", "n": 99},
    ]
    t = D.trending(rows, today=DAY)
    assert [x["card_id"] for x in t] == [3, 1, 2]  # 10×0.906 > 2×2 > 3×3×0.25; day -40 is out of the window
    assert t[1]["score"] == 4.0 and t[1]["counts"] == {"save": 2}
    assert [x["card_id"] for x in D.trending(rows, today=DAY, voivodeship="Podkarpackie")] == [1, 2]
    assert D.trending(rows, today=DAY) == D.trending(list(reversed(rows)), today=DAY)  # deterministic
