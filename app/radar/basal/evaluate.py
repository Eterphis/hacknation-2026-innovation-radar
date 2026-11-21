"""Basal evaluation on the hand-labelled real test set (T021/T038): sector, decision, institution type.

    radar basal-eval [--data ../data/normalized] [--gold eval/basal_gold.jsonl] [--log ../.house/experiments.csv]

Each gold row names a record of the team harvester output (data/normalized/<file>.jsonl, gitignored). The record
goes through the SAME path as production: the `harvester-<file>` mapping from sources.yaml, then
`classify(...)` with the gate's arguments. Scores:
  strict  = prediction equals the first gold label;  lenient = prediction is one of the "a|b" gold labels.
The embedder is whatever RADAR_EMBEDDER selects (hashing | fastembed[:model]), and it is logged with the result.
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
AXES = ("sector", "decision", "institution_type")


def load_gold(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_records(data_dir: Path, files: set[str]) -> dict[tuple[str, str], dict]:
    out = {}
    for f in files:
        p = data_dir / f"{f}.jsonl"
        if not p.exists():
            raise FileNotFoundError(f"{p} — uruchom harvester (python -m radar.refresh) albo podaj --data")
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[(f, r["record_id"])] = r
    return out


def classify_like_gate(payload: dict, source_id: str, kind: str) -> dict:
    from radar.basal.classifier import classify
    from radar.pipeline.normalize import apply_mapping
    from radar.sources.registry import get_source

    spec = get_source(source_id)
    fields, extra = apply_mapping(spec, payload)
    amounts = {k: v for k, v in extra.items() if k.startswith("amount")}
    return classify(title=fields.get("title"), abstract=fields.get("abstract"), keywords=fields.get("keywords"),
                    affiliations=fields.get("affiliations"), region=fields.get("region"), kind=kind, amounts=amounts,
                    declared_institution=extra.get("institution_type"),
                    min_chars=int(spec.options.get("min_abstract_chars", 200)))


def evaluate(gold: list[dict], records: dict) -> dict:
    hit = {a: {"strict": 0, "lenient": 0} for a in AXES}
    errors, conf = [], Counter()
    missing = 0
    t0 = time.perf_counter()
    embedder = None
    for g in gold:
        r = records.get((g["file"], g["record_id"]))
        if r is None:
            missing += 1
            continue
        b = classify_like_gate(r, f"harvester-{g['file']}", g.get("kind", "other"))
        embedder = b["embedder"]
        pred = {"sector": b["sector"]["value"], "decision": b["decision"], "institution_type": b["institution_type"]["value"]}
        conf[(g["gold"]["decision"], pred["decision"])] += 1
        wrong = {}
        for a in AXES:
            options = g["gold"][a].split("|")
            hit[a]["strict"] += pred[a] == options[0]
            hit[a]["lenient"] += pred[a] in options
            if pred[a] not in options:
                wrong[a] = {"gold": g["gold"][a], "pred": pred[a]}
        if wrong:
            errors.append({"i": g["i"], "title": g.get("title"), "wrong": wrong,
                           "reasons": b["reject_reasons"] + b["hold_reasons"]})
    n = len(gold) - missing
    acc = {a: {k: round(v / n, 3) if n else 0.0 for k, v in hit[a].items()} for a in AXES}
    return {"n": n, "missing": missing, "embedder": embedder, "accuracy": acc,
            "decision_confusion": {f"{g}->{p}": c for (g, p), c in sorted(conf.items())},
            "seconds": round(time.perf_counter() - t0, 2), "errors": errors}


def _git_commit() -> str:
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=APP,
                              timeout=5).stdout.strip() or "-"
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "radar", "eval"], capture_output=True, text=True,
                               cwd=APP, timeout=5).stdout.strip()
        return head + ("+dirty" if dirty else "")
    except Exception:
        return "-"


def log_experiment(path: Path, res: dict, command: str, note: str = "") -> str:
    """Append one row to .house/experiments.csv (header: id,parent,commit,idea_id,budget,duration,score,status,
    scorer,time,note,command). score = lenient decision accuracy; the note carries every axis."""
    rows = list(csv.reader(path.open(encoding="utf-8"))) if path.exists() else []
    header = rows[0] if rows else ["id", "parent", "commit", "idea_id", "budget", "duration", "score", "status",
                                   "scorer", "time", "note", "command"]
    ids = [int(r[0].split("-")[1]) for r in rows[1:] if r and r[0].startswith("E-")]
    eid = f"E-{(max(ids) + 1) if ids else 1:03d}"
    a = res["accuracy"]
    ok = a["sector"]["lenient"] >= 0.8 and a["decision"]["strict"] >= 0.85
    text = (f"{eid} basal-eval n={res['n']} embedder={res['embedder']} sector={a['sector']['strict']}/{a['sector']['lenient']} "
            f"decision={a['decision']['strict']} institution={a['institution_type']['strict']}/{a['institution_type']['lenient']} "
            f"(strict/lenient; progi: sektor>=0.8, decyzja>=0.85) {note}").strip()
    row = [eid, "", _git_commit(), "I-006", "", f"{res['seconds']}s", a["decision"]["strict"], "keep" if ok else "discard",
           "radar basal-eval", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), text, command]
    with path.open("a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        if not rows:
            w.writerow(header)
        w.writerow(row)
    return eid


def main(data: str | None, gold: str | None, log: str | None, note: str = "") -> dict:
    gold_path = Path(gold) if gold else APP / "eval" / "basal_gold.jsonl"
    data_dir = Path(data or os.environ.get("RADAR_HARVEST_DIR") or APP.parent / "data" / "normalized")
    g = load_gold(gold_path)
    res = evaluate(g, load_records(data_dir, {x["file"] for x in g}))
    if log:
        res["experiment"] = log_experiment(Path(log), res, "cd app && radar basal-eval --log ../.house/experiments.csv"
                                           + (f"  # RADAR_EMBEDDER={os.environ['RADAR_EMBEDDER']}" if os.environ.get("RADAR_EMBEDDER") else ""), note)
    return res
