"""Agent smoke evaluation on a real LLM (T027): does the tool loop finish, do the citations pass, how slow is it?

    RADAR_LOCAL_LLM_URL=http://localhost:8081/v1 python eval/agent_eval.py --n 8 [--log ../.house/experiments.csv]

Loads the demo snapshots into a throwaway SQLite DB with the offline extractor (fast), then runs `assess` on N
cards with RADAR_LLM_PROVIDERS (default "local": the Bielik model from `docker compose --profile local-llm`).
Reports: share of cards where the model's final answer survived the citation check ("agent LLM ..."), share that
fell back to rules, tool calls per card, citation errors, and LLM latency per call (p50/p95) from `llm_calls`.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--providers", default=os.environ.get("RADAR_AGENT_PROVIDERS", "local"))
    ap.add_argument("--log")
    a = ap.parse_args()

    tmp = Path(tempfile.mkdtemp()) / "agent_eval.db"
    os.environ.update(RADAR_DATABASE_URL=f"sqlite:///{tmp}", RADAR_EAGER="1", RADAR_DEMO_MODE="1",
                      RADAR_LLM_PROVIDERS="mock", RADAR_SOURCES_FILE=str(APP / "sources.yaml"), RADAR_LOG_FORMAT="plain")
    from sqlalchemy import select

    import radar.llm.router as R
    from radar.config import get_settings
    from radar.db import create_all, session
    from radar.models import LlmCall, Record
    from radar.pipeline.assess import assess
    from radar.pipeline.tasks import harvest

    create_all()
    for src in ("demo-zgloszenia", "demo-kohesio", "demo-publikacje"):
        harvest.apply((src,)).get()

    os.environ["RADAR_LLM_PROVIDERS"] = a.providers
    get_settings.cache_clear()
    R._router = None
    rows = []
    t0 = time.perf_counter()
    with session() as s:
        recs = s.scalars(select(Record).where(Record.status == "ready").order_by(Record.priority.desc())).all()[: a.n]
        for rec in recs:
            t = time.perf_counter()
            res = assess(s, rec, rec.card)
            rows.append({"record": rec.id, "by": res["by"], "seconds": round(time.perf_counter() - t, 1),
                         "tools": [x["tool"] for x in res["agent"]["trace"] if x.get("tool") and "reguły" not in str(x.get("by"))],
                         "citation_errors": res["agent"]["citation_errors"][:4], "against_by": res["against_by"],
                         "paths": [p["path"] for p in res["paths"]], "summary": res.get("summary")})
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
            s.commit()
        calls = s.scalars(select(LlmCall).where(LlmCall.provider != "mock")).all()
    lat = sorted(c.latency_ms for c in calls if c.ok)
    n = len(rows)
    out = {"n": n, "providers": a.providers,
           "llm_final_accepted": round(sum(r["by"].startswith("agent LLM") for r in rows) / n, 3) if n else 0,
           "fallback_rules": round(sum("fallback" in r["by"] for r in rows) / n, 3) if n else 0,
           "review_by_llm": round(sum(r["against_by"].startswith("LLM") for r in rows) / n, 3) if n else 0,
           "tool_calls_per_card": round(statistics.mean(len(r["tools"]) for r in rows), 2) if n else 0,
           "llm_calls": len(calls), "llm_errors": sum(not c.ok for c in calls),
           "latency_ms_p50": round(lat[len(lat) // 2], 0) if lat else None,
           "latency_ms_p95": round(lat[int(len(lat) * 0.95) - 1], 0) if lat else None,
           "seconds_total": round(time.perf_counter() - t0, 1)}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if a.log:
        import csv
        from datetime import datetime, timezone

        from radar.basal.evaluate import _git_commit

        p = Path(a.log)
        ids = [int(r[0].split("-")[1]) for r in csv.reader(p.open(encoding="utf-8")) if r and r[0].startswith("E-")]
        eid = f"E-{(max(ids) + 1) if ids else 1:03d}"
        note = (f"{eid} agent-eval n={n} providers={a.providers} llm_final_accepted={out['llm_final_accepted']} "
                f"fallback={out['fallback_rules']} review_llm={out['review_by_llm']} tools/karta={out['tool_calls_per_card']} "
                f"llm_calls={out['llm_calls']} errors={out['llm_errors']} latency p50={out['latency_ms_p50']}ms p95={out['latency_ms_p95']}ms "
                "(dane demo, CPU, llama.cpp)")
        with p.open("a", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerow([eid, "", _git_commit(), "I-006", "", f"{out['seconds_total']}s", out["llm_final_accepted"],
                                     "keep", "eval/agent_eval.py", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     note, f"cd app && RADAR_LOCAL_LLM_URL=... python eval/agent_eval.py --n {n} --providers {a.providers}"])
        print(eid)


if __name__ == "__main__":
    main()
