"""Benchmark a small local LLM (llama.cpp server, OpenAI-compatible API) on N new records.

Measures what a NEW record costs on CPU when the pipeline stays rules-first:

* ``record``  end-to-end for one new record on the small-model path: Basal classification (rules + embeddings),
              pregeneration (radar.pregen, rules) and one small-model call for the slogan ("hasło"),
              constrained by the GBNF grammar radar.pregen.SLOGAN_GBNF.
* ``slogan``  only the small-model call; quality = share of slogans that pass ``radar.pregen.validate_slogan``
              (length, no invented numbers), are Polish and are not just the title copied.
* ``extract`` the full extraction prompt of radar.pipeline.extract, one attempt; quality = share of answers that
              pass its quote validation (verbatim quotes, allowed innovation type).

Start the server separately (not via docker-compose), e.g. 4 vCPU:

    docker run -d --name radar-llm --cpus 4 -p 8081:8080 -v radar-llm-cache:/root/.cache \
        ghcr.io/ggml-org/llama.cpp:server -hf speakleash/Bielik-1.5B-v3.0-Instruct-GGUF:Q8_0 \
        --host 0.0.0.0 --port 8080 -c 4096 -t 4 --alias bielik-1.5b-v3.0-instruct

then, from the repository root, with the app installed (pip install -e app):

    python scripts/bench_local_llm.py --gguf speakleash/Bielik-1.5B-v3.0-Instruct-GGUF:Q8_0 --vcpu 4

Results are appended to .house/experiments-local-llm.csv (merged into .house/experiments.csv after PR #11).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from radar import pregen  # noqa: E402
from radar.basal.classifier import classify  # noqa: E402
from radar.llm.providers import _parse_json  # noqa: E402
from radar.pipeline import extract as X  # noqa: E402

FIELDS = ["id", "time", "model", "gguf", "quant", "vcpu", "task", "n", "mean_s", "p50_s", "p90_s", "quality",
          "out_tok_s", "notes", "command"]
PL = re.compile(r"[ąćęłńóśźż]|\b(i|w|z|na|dla|do|oraz|się|jest)\b", re.I)


# ------------------------------------------------------------------------------------------------ data
def load_records(path: Path, n: int, max_chars: int) -> list[dict]:
    """Normalized harvester records (radar.record/v1) or the demo samples; first ``n`` with enough text."""
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            title = r.get("title")
            title = title[0] if isinstance(title, list) else title
            body = r.get("intro") or r.get("description") or r.get("abstract") or ""
            body = body[0] if isinstance(body, list) else body
            if isinstance(r.get("text"), dict):
                body = " ".join(str(v) for v in r["text"].values() if v) or body
            body = re.sub(r"\s+", " ", body).strip()
            if len(body) < 200 or not title:
                continue
            orgs = [o.get("name") for o in r.get("organizations") or [] if isinstance(o, dict) and o.get("name")]
            region = ((r["region"].get("voivodeships") or [None])[0] if isinstance(r.get("region"), dict)
                      else r.get("region"))
            amount = (r.get("funding") or {}).get("total_value") if isinstance(r.get("funding"), dict) else None
            out.append({"id": r.get("record_id") or r.get("id"), "title": title, "abstract": body[:max_chars],
                        "affiliations": orgs or ([r["institution"]] if r.get("institution") else []),
                        "keywords": r.get("keywords") or [], "region": region,
                        "amounts": {"total": amount} if isinstance(amount, (int, float)) else {}})
            if len(out) >= n:
                break
    return out


# ------------------------------------------------------------------------------------------------ model
class Client:
    def __init__(self, url: str, model: str, max_tokens: int, timeout: float):
        self.url, self.model, self.max_tokens, self.timeout = url.rstrip("/"), model, max_tokens, timeout
        self.out_tokens, self.gen_seconds = 0, 0.0

    def complete(self, system: str, user: str, max_tokens: int | None = None, grammar: str | None = None) -> dict:
        t = time.perf_counter()
        r = httpx.post(self.url + "/chat/completions", timeout=self.timeout, json={
            "model": self.model, "temperature": 0.2, "max_tokens": max_tokens or self.max_tokens,
            **({"grammar": grammar} if grammar else {}),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        r.raise_for_status()
        body = r.json()
        self.gen_seconds += time.perf_counter() - t
        self.out_tokens += (body.get("usage") or {}).get("completion_tokens") or 0
        return _parse_json(body["choices"][0]["message"]["content"])


def as_rec_card(d: dict, labels: dict) -> tuple:
    lab = {k: (v or {}).get("value") if isinstance(v, dict) else v for k, v in (labels.get("labels") or {}).items()}
    rec = SimpleNamespace(id=0, title=d["title"], abstract=d["abstract"], source_id="bench", affiliations=d["affiliations"],
                          amounts=d["amounts"], sector=lab.get("sector"), tech_area=lab.get("tech_area"),
                          innovation_type=lab.get("innovation_type"), institution_type=lab.get("institution_type"),
                          voivodeship=d["region"], cost_level=lab.get("cost_level"))
    card = SimpleNamespace(id=0, solution_name=d["title"], problem_solved=None, summary_pl=None,
                           maturity=labels.get("maturity") or "exploring", score=None, decision="pending",
                           assessment={}, target_users=[], provenance={"provider": "local"})
    return rec, card


# ------------------------------------------------------------------------------------------------ tasks
def run_record_and_slogan(recs: list[dict], cli: Client) -> tuple[list[float], list[float], float]:
    end_to_end, llm_times, good = [], [], 0
    for d in recs:
        t0 = time.perf_counter()
        labels = classify(title=d["title"], abstract=d["abstract"], keywords=d["keywords"],
                          affiliations=d["affiliations"], region=d["region"], amounts=d["amounts"])
        rec, card = as_rec_card(d, labels)
        t1 = time.perf_counter()
        out = pregen.pregenerate(rec, card, complete=lambda s, u: cli.complete(s, u, max_tokens=80,
                                                                              grammar=pregen.SLOGAN_GBNF))
        t2 = time.perf_counter()
        end_to_end.append(t2 - t0)
        llm_times.append(t2 - t1)  # includes rules pregen (microseconds), dominated by the model call
        s = out["slogan"]
        ok = out["slogan_by"] == "local-llm" and PL.search(s) and s.strip().lower() != d["title"].strip().lower()
        good += bool(ok)
        print(f"  {t2 - t0:5.2f}s  {'OK ' if ok else '-- '} {s}", flush=True)
    return end_to_end, llm_times, good / len(recs)


def run_extract(recs: list[dict], cli: Client) -> tuple[list[float], float]:
    times, good = [], 0
    for d in recs:
        text = X.source_text(d["title"], d["abstract"], d["keywords"])
        t = time.perf_counter()
        try:
            out = cli.complete(X.SYSTEM, f"TEKST ŹRÓDŁOWY:\n{text}", max_tokens=700)
            errs = X.validate(out, text)
        except Exception as e:  # noqa: BLE001 - a bad answer is a quality failure, not a crash
            errs = [str(e)[:80]]
        times.append(time.perf_counter() - t)
        good += not errs
        print(f"  {times[-1]:5.2f}s  {'OK ' if not errs else '-- '} {d['title'][:60]}  {'; '.join(errs)[:100]}", flush=True)
    return times, good / len(recs)


# ------------------------------------------------------------------------------------------------ main
def stats(xs: list[float]) -> tuple[float, float, float]:
    s = sorted(xs)
    return statistics.mean(s), s[len(s) // 2], s[min(len(s) - 1, int(len(s) * .9))]


def next_id(path: Path) -> int:
    if not path.exists():
        return 1
    with path.open(encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f)) + 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://localhost:8081/v1")
    ap.add_argument("--model", default="bielik-1.5b-v3.0-instruct", help="server alias")
    ap.add_argument("--gguf", default="speakleash/Bielik-1.5B-v3.0-Instruct-GGUF:Q8_0")
    ap.add_argument("--vcpu", type=int, default=4)
    ap.add_argument("--input", type=Path, default=ROOT / "data" / "normalized" / "ncbr.jsonl")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--max-chars", type=int, default=1200, help="abstract cut, as the pipeline would feed it")
    ap.add_argument("--tasks", default="record,extract")
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--csv", type=Path, default=ROOT / ".house" / "experiments-local-llm.csv")
    ap.add_argument("--note", default="")
    a = ap.parse_args(argv)

    recs = load_records(a.input, a.n, a.max_chars)
    if len(recs) < a.n:
        print(f"only {len(recs)} records with enough text in {a.input}", file=sys.stderr)
    quant = a.gguf.rsplit(":", 1)[-1] if ":" in a.gguf else "?"
    cli = Client(a.url, a.model, 700, a.timeout)
    try:  # warm-up: model load and first prompt cache, not measured
        cli.complete("Odpowiadasz JSON.", 'Zwróć {"ok": true}', max_tokens=20)
    except Exception:  # noqa: BLE001 - only the timing matters here
        pass
    cli.out_tokens, cli.gen_seconds = 0, 0.0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cmd = "python scripts/bench_local_llm.py " + " ".join(argv if argv is not None else sys.argv[1:])
    rows = []
    src = f"{a.input.name} n={len(recs)} cut={a.max_chars}"
    for task in a.tasks.split(","):
        cli.out_tokens, cli.gen_seconds = 0, 0.0
        print(f"== {task} ({len(recs)} records, {a.model}, {a.vcpu} vCPU)", flush=True)
        if task == "record":
            e2e, llm, q = run_record_and_slogan(recs, cli)
            tok = cli.out_tokens / cli.gen_seconds if cli.gen_seconds else 0
            rows.append(("record", e2e, q, tok, f"{src}; Basal + pregen (reguły) + 1 wywołanie małego modelu (hasło)"))
            rows.append(("slogan", llm, q, tok, f"{src}; jakość = hasło przeszło walidację (≤{pregen.SLOGAN_MAX} zn., bez nowych liczb, po polsku, nie sam tytuł)"))
        elif task == "extract":
            t, q = run_extract(recs, cli)
            tok = cli.out_tokens / cli.gen_seconds if cli.gen_seconds else 0
            rows.append(("extract", t, q, tok, f"{src}; prompt extract-v1, 1 próba, jakość = walidacja cytatów"))
    a.csv.parent.mkdir(parents=True, exist_ok=True)
    new = not a.csv.exists()
    i = next_id(a.csv)
    with a.csv.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        if new:
            w.writeheader()
        for k, (task, xs, q, tok, note) in enumerate(rows):
            mean, p50, p90 = stats(xs)
            row = {"id": f"L-{i + k:03d}", "time": now, "model": a.model, "gguf": a.gguf, "quant": quant, "vcpu": a.vcpu,
                   "task": task, "n": len(xs), "mean_s": f"{mean:.2f}", "p50_s": f"{p50:.2f}", "p90_s": f"{p90:.2f}",
                   "quality": f"{q:.3f}", "out_tok_s": f"{tok:.1f}", "notes": (note + (f"; {a.note}" if a.note else "")),
                   "command": cmd}
            w.writerow(row)
            print(f"{row['id']} {task}: mean {mean:.2f}s p50 {p50:.2f}s p90 {p90:.2f}s quality {q:.3f} out {tok:.1f} tok/s")


if __name__ == "__main__":
    main()
