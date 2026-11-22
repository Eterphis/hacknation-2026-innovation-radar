"""End-to-end smoke test against a running stack (compose, k8s, public URL).

    python scripts/smoke.py http://localhost:8088

Checks every public endpoint the UI uses, submits one idea and waits until it has a scored card (the jury path),
and prints one line per check. Exit code 1 if anything fails. Standard library only.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8088").rstrip("/")
fails = 0


def call(path, body=None, method=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"}, method=method or ("POST" if body is not None else "GET"))
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        ms = (time.perf_counter() - t0) * 1000
        ctype = r.headers.get("content-type", "")
        return (json.loads(raw) if "json" in ctype else raw.decode("utf-8", "replace")), ms


def check(name, path, test=lambda d: True, body=None):
    global fails
    try:
        d, ms = call(path, body)
        ok = bool(test(d))
    except (urllib.error.URLError, ValueError, KeyError, IndexError, TypeError) as e:
        d, ms, ok = None, 0, False
        print(f"FAIL {name:28} {path}  {type(e).__name__}: {e}")
        fails += 1
        return None
    print(f"{'ok  ' if ok else 'FAIL'} {name:28} {ms:7.0f} ms  {path}")
    fails += not ok
    return d


check("health", "/healthz")
check("ready (db + broker)", "/readyz")
check("static app", "/", lambda d: "Radar Innowacji" in d)
check("sources", "/api/sources", lambda d: len(d) > 0)
check("stats", "/api/stats", lambda d: "records_by_status" in d)
ideas = check("ideas", "/api/ideas?limit=5", lambda d: d["total"] > 0 and d["items"])
check("insights", "/api/insights", lambda d: "kpi" in d)
check("regions (map)", "/api/regions", lambda d: len(d["regions"]) == 16)
check("graph", "/api/graph?limit=60", lambda d: d["nodes"])
check("feed (reels)", "/api/feed?limit=5", lambda d: len(d) > 0)
check("personas", "/api/personas", lambda d: len(d) == 6)
check("persona investors", "/api/personas/inwestorzy?limit=5", lambda d: d["items"])
check("match", "/api/match?role=samorzady&voivodeship=podkarpackie&budget=sredni&goal=wdrozenie", lambda d: d["items"] and d["items"][0]["why"])
check("clusters topics", "/api/clusters", lambda d: d["clusters"])
check("clusters markets", "/api/clusters?mode=rynki", lambda d: d["clusters"])
check("deployments", "/api/deployments?side=odbiorca", lambda d: d["items"])
check("deployments contractor", "/api/deployments?side=wykonawca", lambda d: len(d["regions"]) == 16)
if ideas:
    cid = ideas["items"][0]["card_id"]
    check("card + business + investor", f"/api/cards/{cid}", lambda d: d["business"] and d["investor"]["readiness"])
    check("memo (investor)", f"/api/cards/{cid}/memo", lambda d: "Memo inwestycyjne" in d)
    check("memo (contractor)", f"/api/cards/{cid}/memo?kind=wykonawca", lambda d: "Specyfikacja wdrożenia" in d)
check("metrics", "/metrics", lambda d: "radar_" in d)

# the jury path: submit an idea and wait for a scored card
sub = check("submit idea", "/api/ingest/zgloszenia/manual", lambda d: d.get("raw_id"), body={
    "title": f"Smoke {int(time.time())}: wspólny system rezerwacji sal sportowych gmin i szkół",
    "description": "Gmina i szkoły udostępniają sale sportowe mieszkańcom przez jeden kalendarz online. Kluby rezerwują terminy, dyrektorzy widzą obłożenie, gmina rozlicza opłaty. Działa w jednej gminie od roku.",
    "institution": "Urząd Gminy", "institution_type": "jst", "region": "lubelskie"})
if sub:
    t0 = time.time()
    while time.time() - t0 < 90:
        st, _ = call(sub["track"])
        if st["card_id"]:
            break
        time.sleep(1)
    ok = bool(st["card_id"])
    print(f"{'ok  ' if ok else 'FAIL'} {'submission -> scored card':28} {(time.time() - t0) * 1000:7.0f} ms  card {st['card_id']}")
    fails += not ok
watch = check("watchlist", "/api/watch", lambda d: d["token"], body={"profile": {"role": "inwestorzy"}, "min_match": 50})
if watch:
    check("watchlist feed", f"/api/watch/{watch['token']}/feed.xml", lambda d: "<feed" in d)

print(f"\n{'ALL OK' if not fails else f'{fails} FAILED'}  ({BASE})")
sys.exit(1 if fails else 0)
