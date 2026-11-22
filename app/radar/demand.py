"""Demand vs supply per voivodeship and "on the rise in your region", as pure functions (no LLM, no database).

Demand signals are anonymous and aggregated before they are stored: the wizard profile ("Dopasuj") becomes daily
counters per (day, role, voivodeship, sector, budget) and the card beacon becomes daily counters per
(day, card, kind, voivodeship). No identifier, browser id, IP or free text is kept, only allowed values from fixed
vocabularies, so a row cannot point at a person. Small cells (< MIN_CELL profiles) are suppressed in the output.

Planned tables (migration 0006, after PR #36 merges; one row per key, `n` incremented):
  demand_signals(day DATE, role, voivodeship, sector, budget, n)    unique(day, role, voivodeship, sector, budget)
  card_signals(day DATE, card_id FK cards.id, kind, voivodeship, n) unique(day, card_id, kind, voivodeship)
The functions below take plain row dicts with those fields, so they work the same on the tables, in tests and on
any export.

- `profile_rows(profile, day)` -> counter rows for one wizard submission (unknown values dropped, not stored).
- `signal_row(card_id, kind, voivodeship, day)` -> one beacon counter row, or None for an unknown kind.
- `demand_map(profiles, signals, likes, supply, sector=)` -> per voivodeship: demand (profiles, saves, deals,
  compares, likes, weighted index) vs supply (ideas), with the ratio and a plain label.
- `trending(signals, today=, voivodeship=)` -> cards ranked by recent signals with exponential time decay.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from radar.basal import taxonomy as T
from radar.basal.embed import fold

ROLES = ("inwestorzy", "samorzady", "uczelnie", "szkoly", "startupy", "innowatorzy")
BUDGETS = ("niski", "sredni", "wysoki", "bardzo_wysoki")
KINDS = ("save", "deal", "compare")
# weights of the demand index: a stated need (profile) or a deal-pipeline entry weighs more than a like
WEIGHTS = {"profile": 3, "deal": 3, "save": 2, "compare": 1, "like": 1}
MIN_CELL = 3
HALF_LIFE_DAYS = 7
WINDOW_DAYS = 30
METHOD = (f"indeks popytu = {WEIGHTS['profile']}×profile + {WEIGHTS['deal']}×portfel + {WEIGHTS['save']}×zapisy + "
          f"{WEIGHTS['compare']}×porównania + {WEIGHTS['like']}×polubienia; podaż = liczba pomysłów z regionu; "
          f"komórki z mniej niż {MIN_CELL} profilami są ukryte")


def norm_voivodeship(v: str | None) -> str | None:
    """Any spelling ('Podkarpackie', 'podkarpackie', 'slaskie') -> the display name used by the app, else None."""
    if not v:
        return None
    k = fold(v).strip().replace(" ", "-")
    return T.VOIVODESHIPS.get(k) or (v if v in T.VOIVODESHIPS.values() else None)


def profile_rows(profile: dict, day: date | None = None) -> list[dict]:
    """One counter row per chosen sector (or one row without a sector). Anything not in the vocabularies is
    dropped; a profile without a known role yields nothing."""
    role = profile.get("role")
    if role not in ROLES:
        return []
    sectors = profile.get("sectors") or []
    if isinstance(sectors, str):
        sectors = sectors.split(",")
    sectors = sorted({s for s in sectors if s in T.SECTORS})[:6] or [None]
    budget = profile.get("budget") if profile.get("budget") in BUDGETS else None
    woj = norm_voivodeship(profile.get("voivodeship"))
    d = (day or date.today()).isoformat()
    return [{"day": d, "role": role, "voivodeship": woj, "sector": s, "budget": budget, "n": 1} for s in sectors]


def signal_row(card_id: int, kind: str, voivodeship: str | None = None, day: date | None = None) -> dict | None:
    if kind not in KINDS or not isinstance(card_id, int) or card_id <= 0:
        return None
    return {"day": (day or date.today()).isoformat(), "card_id": card_id, "kind": kind,
            "voivodeship": norm_voivodeship(voivodeship), "n": 1}


def merge(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    """Sum `n` over identical keys (what the table's upsert does)."""
    acc: dict[tuple, int] = defaultdict(int)
    for r in rows:
        acc[tuple(r.get(k) for k in keys)] += int(r.get("n") or 0)
    return [{**dict(zip(keys, k)), "n": n} for k, n in acc.items()]


def demand_map(profiles: list[dict], signals: list[dict], likes: list[dict], supply: list[dict],
               sector: str | None = None, roles: tuple[str, ...] | None = None) -> dict:
    """profiles: demand_signals rows; signals: card_signals rows with the card's `sector` and `card_voivodeship`;
    likes: {card_id, sector, card_voivodeship, n}; supply: {voivodeship, sector, n} (ideas per region).
    Card signals and likes count where the idea is (they show interest in that region's supply); profiles count
    where the person is."""
    def ok(s):
        return sector is None or s == sector

    cells = {w: {"profiles": 0, "save": 0, "deal": 0, "compare": 0, "like": 0, "supply": 0} for w in T.VOIVODESHIPS.values()}
    for r in profiles:
        w = norm_voivodeship(r.get("voivodeship"))
        if w and ok(r.get("sector")) and (roles is None or r.get("role") in roles):
            cells[w]["profiles"] += int(r.get("n") or 0)
    for r in signals:
        w = norm_voivodeship(r.get("card_voivodeship") or r.get("voivodeship"))
        if w and ok(r.get("sector")) and r.get("kind") in KINDS:
            cells[w][r["kind"]] += int(r.get("n") or 0)
    for r in likes:
        w = norm_voivodeship(r.get("card_voivodeship") or r.get("voivodeship"))
        if w and ok(r.get("sector")):
            cells[w]["like"] += int(r.get("n") or 0)
    for r in supply:
        w = norm_voivodeship(r.get("voivodeship"))
        if w and ok(r.get("sector")):
            cells[w]["supply"] += int(r.get("n") or 0)

    regions = []
    for w, c in cells.items():
        suppressed = 0 < c["profiles"] < MIN_CELL
        profiles_n = 0 if suppressed else c["profiles"]
        index = (WEIGHTS["profile"] * profiles_n + sum(WEIGHTS[k] * c[k] for k in ("deal", "save", "compare", "like")))
        ratio = round(index / max(1, c["supply"]), 2)
        label = ("brak danych" if not index and not c["supply"] else
                 "niedobór podaży" if index >= 2 * max(1, c["supply"]) else
                 "nadwyżka podaży" if index * 2 < c["supply"] else "równowaga")
        regions.append({"voivodeship": w, "demand": {"profiles": profiles_n, "profiles_suppressed": suppressed,
                                                      "saves": c["save"], "deals": c["deal"], "compares": c["compare"],
                                                      "likes": c["like"], "index": index},
                        "supply": c["supply"], "ratio": ratio, "label": label})
    regions.sort(key=lambda r: (-r["ratio"], -r["demand"]["index"], r["voivodeship"]))
    return {"sector": sector, "regions": regions, "method": METHOD,
            "totals": {"demand_index": sum(r["demand"]["index"] for r in regions), "supply": sum(r["supply"] for r in regions)}}


def trending(signals: list[dict], today: date | None = None, voivodeship: str | None = None,
             half_life_days: float = HALF_LIFE_DAYS, window_days: int = WINDOW_DAYS, n: int = 10) -> list[dict]:
    """signals: card_signals rows (+ like rows with kind 'like'), each with `day`, `card_id`, `kind`, `n` and the
    region it counts for (`voivodeship`: the viewer's region from the beacon, else the card's `card_voivodeship`).
    Score = sum of weight × n × 0.5^(age / half-life) over the last `window_days`; ties by card id (deterministic)."""
    today = today or date.today()
    woj = norm_voivodeship(voivodeship)
    acc: dict[int, dict] = {}
    for r in signals:
        kind = r.get("kind")
        if kind not in WEIGHTS or kind == "profile":
            continue
        try:
            d = date.fromisoformat(str(r["day"])[:10])
        except (KeyError, ValueError):
            continue
        age = (today - d).days
        if age < 0 or age > window_days:
            continue
        if woj and norm_voivodeship(r.get("voivodeship") or r.get("card_voivodeship")) != woj:
            continue
        cnt = int(r.get("n") or 0)
        a = acc.setdefault(r["card_id"], {"card_id": r["card_id"], "score": 0.0, "counts": defaultdict(int), "last_day": d})
        a["score"] += WEIGHTS[kind] * cnt * 0.5 ** (age / half_life_days)
        a["counts"][kind] += cnt
        a["last_day"] = max(a["last_day"], d)
    out = sorted(acc.values(), key=lambda a: (-a["score"], a["card_id"]))[:n]
    return [{"card_id": a["card_id"], "score": round(a["score"], 3), "counts": dict(a["counts"]),
             "last_day": a["last_day"].isoformat()} for a in out]
