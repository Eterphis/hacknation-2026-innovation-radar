"""basal-eval: joins gold labels with harvester records, scores strict/lenient, logs to experiments.csv."""

import csv
import json

from radar.basal.classifier import classify
from radar.basal.embed import calibration, closeness
from radar.basal.evaluate import evaluate, log_experiment


def _rec(rid, title, text, orgs, voiv):
    return {"schema": "radar.record/v1", "record_id": rid, "title": title, "text_for_llm": f"Tytuł: {title}\n\nOpis projektu:\n{text}",
            "organizations": [{"name": o} for o in orgs], "region": {"voivodeships": [voiv]}, "funding": {}}


def test_eval_scores_and_logs(tmp_path):
    recs = {("interreg", "a"): _rec("a", "Wspólna oczyszczalnia ścieków", "Gmina opracowała i wdrożyła system oczyszczania ścieków "
                                    "w małych gminach z osadami czynnymi; model działania przetestowano w pilotażu. " * 3,
                                    ["Gmina Jastków"], "lubelskie"),
            ("ncbr", "b"): _rec("b", "Platforma reklamowa", "Firma opracowała system predykcji kampanii reklamowych, algorytm "
                                "działa w chmurze i optymalizuje budżety reklamowe klientów. " * 3, ["Netarch Sp. z o.o."], "małopolskie")}
    gold = [{"i": 0, "file": "interreg", "kind": "project", "record_id": "a",
             "gold": {"sector": "E_srodowisko", "decision": "accept", "institution_type": "jst"}},
            {"i": 1, "file": "ncbr", "kind": "solution", "record_id": "b",
             "gold": {"sector": "C_przemysl|J_ict", "decision": "reject", "institution_type": "firma"}}]
    res = evaluate(gold, recs)
    assert res["n"] == 2 and res["accuracy"]["decision"]["strict"] == 1.0
    assert res["accuracy"]["institution_type"]["strict"] == 1.0
    assert res["accuracy"]["sector"]["lenient"] >= res["accuracy"]["sector"]["strict"]
    log = tmp_path / "experiments.csv"
    assert log_experiment(log, res, "radar basal-eval") == "E-001"
    assert log_experiment(log, res, "radar basal-eval") == "E-002"
    rows = list(csv.DictReader(log.open(encoding="utf-8")))
    assert rows[1]["id"] == "E-002" and "basal-eval n=2" in rows[1]["note"] and rows[1]["scorer"] == "radar basal-eval"


def test_institution_from_org_names_not_description():
    b = classify(title="Bezpieczne pogranicze", abstract="Projekt realizują służby; sa to działania z udziałem firm, np. Kenbit sp. z o.o. "
                 "jako dostawcy. Opracowano wspólną procedurę reagowania i program szkoleń. " * 3,
                 affiliations=["Komenda Wojewódzka Policji w Krakowie"], kind="project", min_chars=80)
    assert b["institution_type"]["value"] == "inna_publiczna" and b["decision"] == "accept"
    ngo = classify(title="Parki", abstract="Fundacja opracowała nowy program usług turystycznych w parkach i model współpracy. " * 4,
                   affiliations=["Fundacja Doliny Pałaców"], kind="project", min_chars=80)
    assert ngo["decision"] == "hold" and any("pozarządowe" in r for r in ngo["hold_reasons"])


def test_calibration_scale():
    c = calibration("fastembed:intfloat/multilingual-e5-small")
    assert c["lo"] < c["hi"] and c["similar_min"] < c["dup_min"]
    assert closeness(c["similar_min"], "fastembed:intfloat/multilingual-e5-small") == 0.0
    assert closeness(1.0, "hashing-stem6+char4") == 1.0


def test_company_form_in_capitals_without_dots():
    """PR #11 review, risk 5: "S.A." needed dots after the Slovak "sa" fix, so "PGE SA" stopped being a company."""
    body = "Opracowano nowy system monitoringu sieci i wdrożono go w zakładach. " * 4
    for org in ("PGE Dystrybucja SA", "Orlen S.A.", "Comarch SA, Kraków"):
        b = classify(title="Monitoring", abstract=body, affiliations=[org], kind="project", min_chars=80)
        assert b["institution_type"]["value"] == "firma", org
    sk = classify(title="Hranice", abstract=body, affiliations=["Krajské riaditeľstvo Policajného zboru, s ktorým sa spolupracuje"],
                  kind="project", min_chars=80)
    assert sk["institution_type"]["value"] != "firma"  # lower-case Slovak "sa" is a word, not a company form
