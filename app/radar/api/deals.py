"""Tools for the people who decide whether an idea gets built: investors and implementers.

- /api/cards/{id}/memo     one-page investment memo or implementation spec (print to PDF), assembled from fields the
                           pipeline already computed: no new facts, no LLM call at request time
- /api/watch               save a "Dopasuj radar" profile behind an anonymous token; Atom feed + optional webhook
- /api/deployments         municipality side: ready solutions + who can deliver + how to pay;
                           implementer side: where to sell (regions, adopters, revenue potential)
- /api/v1/*                partner API (funds, agencies) with API keys and a per-key rate limit
"""

from __future__ import annotations

import html
import os
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from radar.basal import taxonomy as T
from radar.basal.classifier import label_pl
from radar.db import session
from radar.models import Card, Record, Watchlist

router = APIRouter(prefix="/api")
v1 = APIRouter(prefix="/api/v1", tags=["partner API"])
LVL_PL = {"exploring": "badania", "tech_ready": "technologia gotowa", "business_ready": "gotowe do wdrożenia", "market_ready": "na rynku"}


def zl(n) -> str:
    if n is None:
        return "—"
    n = float(n)
    if n >= 1e9:
        return f"{n / 1e9:.1f} mld zł".replace(".", ",")
    if n >= 1e6:
        return f"{n / 1e6:.1f} mln zł".replace(".", ",")
    return f"{round(n / 1000):,} tys. zł".replace(",", " ")


def full_card(s, c: Card) -> dict:
    """Business case + investor signals for one card (the same numbers the UI and the memo show)."""
    from radar.business import business_case
    from radar.investor import signals

    r = c.record
    bc = business_case(r, c) if c.maturity else None
    sig = signals(s, r, c, bc) if bc else None
    return {"record": r, "card": c, "business": bc, "investor": sig}


@router.get("/cards/{card_id}/signals")
def card_signals(card_id: int):
    with session() as s:
        c = s.get(Card, card_id)
        if c is None:
            raise HTTPException(404)
        f = full_card(s, c)
        return {"card_id": c.id, "business": f["business"], "investor": f["investor"]}


# ------------------------------------------------------------------------------------------------ memo
@router.get("/cards/{card_id}/memo", response_class=HTMLResponse)
def memo(card_id: int, kind: str = "inwestor", auto: bool = False):
    """kind: inwestor (investment memo) | wykonawca (implementation spec). ?auto=1 opens the print dialog (PDF)."""
    with session() as s:
        c = s.get(Card, card_id)
        if c is None or not c.maturity:
            raise HTTPException(404)
        f = full_card(s, c)
        return HTMLResponse(render_memo(f, kind, auto_print=auto))


def _li(items) -> str:
    return "".join(f"<li>{html.escape(str(x))}</li>" for x in items if x)


def render_memo(f: dict, kind: str, auto_print: bool = False) -> str:
    r, c, bc, sig = f["record"], f["card"], f["business"], f["investor"]
    e = html.escape
    a = c.assessment or {}
    path = (a.get("paths") or [{}])[0]
    risks = a.get("risks") or []
    title = c.solution_name or r.title or "Pomysł"
    org = ", ".join((r.affiliations or [])[:2]) or "—"
    where = " · ".join(x for x in [r.voivodeship] if x) or "Polska"
    rd = sig["readiness"]
    adj = sig["adjusted"]
    inv = kind != "wykonawca"
    kpis = ([("Wartość licencji / spin-off", zl(adj["licence_or_spinoff_pln"])), ("Szansa wdrożenia", f"{adj['success_probability']:.0%}"),
             ("Rynek 3 lata (SOM)", zl(bc["market"]["som_3y_pln"])), ("Gotowość inwestycyjna", f"{rd['score']}/100")] if inv else
            [("Koszt wdrożenia", zl(bc["deploy_cost_pln"])), ("Oszczędność vs. budowa od zera", zl(bc["savings_per_adopter_pln"])),
             ("Zwrot", bc["payback"]), ("Potencjalni odbiorcy", f"{bc['adopters']['count']:,}".replace(",", " "))])
    ip, tr, tm, cm, cp = sig["ip"], sig["traction"], sig["team"], sig["commercial"], sig["comparables"]
    ip_pl = {"none": "brak śladów ochrony w danych", "weak": "instytucja ma patenty w bazie", "medium": "zgłoszenie / wynalazek wspomniany w opisie", "strong": "patent udzielony"}[ip["strength"]]
    evidence = [
        f"Ochrona IP: {ip_pl}" + (f" ({ip['org_patents']} patentów instytucji w bazie)" if ip["org_patents"] else ""),
        f"Trakcja: {zl(tr['public_funding_pln'])} publicznych środków instytucji w {tr['grants']} projektach" if tr["grants"] else "Trakcja: brak innych finansowanych projektów instytucji w bazie",
        f"Zespół: {tm['people']} osób" + (f", m.in. {', '.join(p['name'] for p in tm['top'][:2])}" if tm["top"] else "") if tm["people"] else None,
        f"Komercjalizacja: {cm['route']}" if cm["route"] else None,
        (f"Porównywalne: mediana {zl(cp['median_pln'])} z {len(cp['items'])} zrealizowanych projektów w sektorze" if cp["median_pln"] else None),
    ]
    steps = [st.get("step") + (f" — {st.get('who')}" if st.get("who") else "") for st in (path.get("steps") or [])[:4] if st.get("step")]
    funding = [x["programme"] + f" ({x['for']})" for x in bc["funding"]]
    src = r.url or (f"https://doi.org/{r.doi}" if r.doi else "")
    kpi_html = "".join(f"<div class='k'><small>{e(k)}</small><b>{e(v)}</b></div>" for k, v in kpis)
    risk_html = "".join(f"<tr><td>{e(x.get('risk', ''))}</td><td>{e(x.get('level', ''))}</td><td>{e(x.get('mitigation', ''))}</td></tr>" for x in risks[:4])
    comp_html = "".join(f"<li>{e(x['title'])} — {zl(x['amount'])}{', ' + e(x['voivodeship']) if x.get('voivodeship') else ''} ({x['year'] or '—'})</li>" for x in cp["items"][:3])
    implementers = []
    if not inv:
        from radar.investor import implementers as impl
        with session() as s:
            implementers = impl(s, r.sector, r.voivodeship)
    impl_html = "".join(f"<li>{e(o['name'])} — {e(o['voivodeship'] or '—')}, {o['ready']} gotowych rozwiązań w sektorze</li>" for o in implementers)
    doc = "Memo inwestycyjne" if inv else "Specyfikacja wdrożenia"
    return f"""<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(doc)} — {e(title[:60])}</title><style>
:root{{--bg:#F4EFE6;--paper:#FFFDF9;--ink:#1D1B18;--ink2:#55514A;--red:#BE1A34;--line:#E4DCCD}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
.page{{max-width:820px;margin:24px auto;background:var(--paper);padding:36px 44px;border-radius:18px;box-shadow:0 10px 30px rgba(60,40,20,.12)}}
header{{display:flex;justify-content:space-between;gap:16px;border-bottom:3px solid var(--red);padding-bottom:12px}}
.brand{{font-weight:800;color:var(--red);letter-spacing:.02em}} h1{{font-size:22px;line-height:1.25;margin:10px 0 4px}}
.meta{{color:var(--ink2);font-size:13px}} h2{{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--red);margin:20px 0 6px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:16px 0}} .k{{background:var(--bg);border-radius:12px;padding:10px 12px}}
.k small{{display:block;color:var(--ink2);font-size:11px}} .k b{{font-size:18px}} ul{{margin:4px 0;padding-left:18px}}
table{{width:100%;border-collapse:collapse;font-size:13px}} td{{border-top:1px solid var(--line);padding:5px 6px;vertical-align:top}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:20px}} .note{{color:var(--ink2);font-size:11px;margin-top:18px;border-top:1px solid var(--line);padding-top:8px}}
.bar{{max-width:820px;margin:16px auto 0;display:flex;gap:8px;justify-content:flex-end}} .bar a,.bar button{{font:600 13px system-ui;padding:8px 14px;border-radius:10px;border:0;background:var(--red);color:#fff;text-decoration:none;cursor:pointer}}
.bar a.alt{{background:var(--paper);color:var(--ink)}}
@media (max-width:640px){{.page{{padding:20px;margin:0;border-radius:0}}.kpis,.two{{grid-template-columns:1fr 1fr}}}}
@media print{{body{{background:#fff}}.bar{{display:none}}.page{{box-shadow:none;margin:0;padding:0;max-width:none}}@page{{margin:14mm}}}}
</style></head><body>
<div class="bar"><a class="alt" href="?kind={'wykonawca' if inv else 'inwestor'}">{'Wersja dla wykonawcy' if inv else 'Wersja dla inwestora'}</a><button onclick="print()">Zapisz PDF</button></div>
<article class="page"><header><div><div class="brand">Radar Innowacji · {e(doc)}</div><h1>{e(title)}</h1>
<div class="meta">{e(org)} · {e(where)} · {e(label_pl('sector', r.sector) if r.sector else '—')} · dojrzałość: {e(LVL_PL.get(c.maturity, '—'))}</div></div>
<div class="meta" style="text-align:right;white-space:nowrap">{datetime.now(timezone.utc):%d.%m.%Y}<br>karta #{c.id}</div></header>
<div class="kpis">{kpi_html}</div>
<div class="two"><div><h2>Problem</h2><p>{e((c.problem_solved or '')[:420])}</p></div><div><h2>Co jest nowe</h2><p>{e((c.what_is_new or c.summary_pl or '')[:420])}</p></div></div>
<div class="two"><div><h2>{'Dowody dla inwestora' if inv else 'Dlaczego to zadziała'}</h2><ul>{_li(evidence if inv else [f'Działa u twórcy: {org}', f'Dojrzałość: {LVL_PL.get(c.maturity, "—")}', *evidence[1:3]])}</ul></div>
<div><h2>Rynek</h2><ul>{_li([f"TAM {zl(bc['market']['tam_pln'])}, SAM {zl(bc['market']['sam_pln'])}, SOM 3 lata {zl(bc['market']['som_3y_pln'])}", f"Odbiorcy: {bc['adopters']['count']:,} {bc['adopters']['who']}".replace(',', ' '), f"Model: {bc['model']}"])}</ul></div></div>
<h2>{'Następny krok i ścieżka' if inv else 'Plan wdrożenia'}</h2><p><b>{e(path.get('path') or '—')}</b>{(' — ' + e(path.get('why'))) if path.get('why') else ''}</p><ul>{_li(steps)}</ul>
{'' if inv else f'<h2>Kto może wdrożyć</h2><ul>{impl_html or "<li>twórca rozwiązania</li>"}</ul>'}
<div class="two"><div><h2>Finansowanie</h2><ul>{_li(funding) or '<li>—</li>'}</ul></div><div><h2>Porównywalne projekty</h2><ul>{comp_html or '<li>brak w bazie</li>'}</ul></div></div>
<h2>Ryzyka i mitygacje</h2><table>{risk_html or '<tr><td>—</td></tr>'}</table>
{f"<h2>Korekta wyceny</h2><ul>{_li(adj['reasons']) or '<li>bez korekty (brak dodatkowych dowodów)</li>'}</ul>" if inv else ''}
<div class="note">Założenia: {e('; '.join(bc['assumptions'][:4]))}. Źródło: {e(r.source_id)}{(' — ' + e(src)) if src else ''}.
Memo złożone automatycznie z danych publicznych i reguł (bez modelu językowego); liczby są szacunkami do weryfikacji w due diligence.</div>
</article>{'<script>addEventListener("load",()=>setTimeout(print,300))</script>' if auto_print else ''}</body></html>"""


# ------------------------------------------------------------------------------------------------ watchlists
class WatchIn(BaseModel):
    profile: dict = Field(default_factory=dict)
    min_match: int = 70
    webhook_url: str | None = None


def _match_items(profile: dict, limit: int = 40) -> list[dict]:
    from radar.api.explore import match

    p = {k: profile.get(k) for k in ("role", "voivodeship", "budget", "goal")}
    sectors = profile.get("sectors")
    return match(role=p["role"] or "innowatorzy", voivodeship=p["voivodeship"] or None,
                 sectors=",".join(sectors) if isinstance(sectors, list) else sectors, budget=p["budget"] or "wysoki",
                 stage="tech_ready" if p["goal"] == "zysk" else "exploring", goal=p["goal"] or "wdrozenie", limit=limit)["items"]


@router.post("/watch", status_code=201)
def watch_create(w: WatchIn, request: Request):
    if w.webhook_url and not w.webhook_url.startswith("https://"):
        raise HTTPException(422, "webhook musi być https://")
    tok = secrets.token_urlsafe(18)
    with session() as s:
        s.add(Watchlist(token=tok, profile=w.profile, min_match=max(0, min(100, w.min_match)), webhook_url=w.webhook_url))
    base = str(request.base_url).rstrip("/")
    return {"token": tok, "feed_url": f"{base}/api/watch/{tok}/feed.xml", "json_url": f"{base}/api/watch/{tok}"}


def _watch(s, token: str) -> Watchlist:
    w = s.scalar(select(Watchlist).where(Watchlist.token == token))
    if w is None:
        raise HTTPException(404)
    return w


@router.get("/watch/{token}")
def watch_items(token: str):
    with session() as s:
        w = _watch(s, token)
        prof, mm = dict(w.profile), w.min_match
    items = [i for i in _match_items(prof) if i["match"] >= mm]
    items.sort(key=lambda i: -i["card_id"])  # newest first: a feed is about what's new
    return {"profile": prof, "min_match": mm, "items": items}


@router.get("/watch/{token}/feed.xml")
def watch_feed(token: str, request: Request):
    d = watch_items(token)
    base = str(request.base_url).rstrip("/")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    e = html.escape
    entries = "".join(
        f"<entry><id>urn:radar:card:{i['card_id']}</id><title>{e(i['title'] or '')}</title><updated>{now}</updated>"
        f"<link href=\"{base}/#/odkrywaj?card={i['card_id']}\"/><link rel=\"related\" href=\"{base}/api/cards/{i['card_id']}/memo\"/>"
        f"<summary>Dopasowanie {i['match']}% · {e('; '.join(i['why']))} · {e(zl(i['business']['metric']))}</summary></entry>"
        for i in d["items"][:30])
    xml = (f"<?xml version=\"1.0\" encoding=\"utf-8\"?><feed xmlns=\"http://www.w3.org/2005/Atom\"><id>urn:radar:watch:{e(token[:8])}</id>"
           f"<title>Radar Innowacji — dopasowane do Ciebie</title><updated>{now}</updated>{entries}</feed>")
    return Response(xml, media_type="application/atom+xml")


def notify_watchlists() -> dict:
    """Daily (beat): POST new matches (cards newer than the last notification) to watchlists with a webhook."""
    import httpx

    sent = 0
    with session() as s:
        rows = [(w.id, w.token, dict(w.profile), w.min_match, w.webhook_url, w.last_notified_card)
                for w in s.scalars(select(Watchlist).where(Watchlist.webhook_url.is_not(None)))]
    for wid, tok, prof, mm, url, last in rows:
        new = [i for i in _match_items(prof) if i["match"] >= mm and i["card_id"] > last]
        if not new:
            continue
        try:
            httpx.post(url, json={"watch": tok[:8], "items": [{k: i[k] for k in ("card_id", "title", "match", "why")} for i in new[:20]]},
                       timeout=10)
            sent += 1
        except httpx.HTTPError:
            continue
        with session() as s:
            w = s.get(Watchlist, wid)
            w.last_notified_card = max(i["card_id"] for i in new)
    return {"notified": sent}


# ------------------------------------------------------------------------------------------------ deployments
COSTS = ["niski", "sredni", "wysoki", "bardzo_wysoki"]


@router.get("/deployments")
def deployments(side: str = "odbiorca", voivodeship: str | None = None, sectors: str | None = None,
                budget: str = "wysoki", limit: int = 12):
    """side=odbiorca: ready solutions for my institution + who can deliver + how to pay.
    side=wykonawca: where to sell (per-region adopters and revenue potential) + solutions worth licensing."""
    from radar.api.explore import _filters, idea_dict
    from radar.business import adopter_key, adopters_for, business_case, dedup_key, is_infrastructure
    from radar.investor import _org_key, implementers

    want = set(filter(None, (sectors or "").split(",")))
    bmax = COSTS.index(budget) if budget in COSTS else 2
    with session() as s:
        q = (select(Record).join(Card, Card.record_id == Record.id)
             .where(_filters(maturity="business_ready,market_ready"), Card.decision != "rejected")
             .order_by(Card.score.desc().nulls_last()).limit(500))
        out, seen = [], set()
        for r in s.scalars(q):
            if is_infrastructure(r) or (want and r.sector not in want):
                continue
            if COSTS.index(r.cost_level) > bmax if r.cost_level in COSTS else False:
                continue
            k = dedup_key(r)
            if k in seen:
                continue
            seen.add(k)
            bc = business_case(r, r.card)
            d = idea_dict(r)
            d["deploy_cost_pln"] = bc["deploy_cost_pln"]
            d["savings_pln"] = bc["savings_per_adopter_pln"]
            d["payback"] = bc["payback"]
            d["funding"] = [x["programme"] for x in bc["funding"][:3]]
            d["implementers"] = [{"name": (r.affiliations or ["twórca"])[0], "voivodeship": r.voivodeship, "role": "twórca"}] + [
                {**o, "role": "dostawca w sektorze"} for o in implementers(s, r.sector, voivodeship, exclude=_org_key(r.extra, r.affiliations), n=2)]
            d["adopter_key"] = adopter_key(r)
            out.append(d)
            if len(out) >= 120:
                break
        if side == "wykonawca":
            regions = {}
            for v in T.VOIVODESHIPS.values():
                pot, adopters = 0.0, 0
                for d in out:
                    a = adopters_for(d["adopter_key"], v)
                    reg = a["regional"] or 0
                    pot += reg * d["deploy_cost_pln"] * .02
                    adopters += reg
                regions[v] = {"voivodeship": v, "revenue_3y_pln": round(pot), "adopters": adopters,
                              "local_supply": sum(1 for d in out if d["voivodeship"] == v)}
            ranked = sorted(regions.values(), key=lambda x: -x["revenue_3y_pln"] / (1 + x["local_supply"]))
            return {"side": side, "regions": ranked, "items": sorted(out, key=lambda d: -d["savings_pln"])[:limit],
                    "total": len(out)}
    if voivodeship:
        out.sort(key=lambda d: (d["voivodeship"] != voivodeship, -(d["score"] or 0)))
    return {"side": "odbiorca", "items": out[:limit], "total": len(out)}


# ------------------------------------------------------------------------------------------------ partner API
_BUCKETS: dict[str, list[float]] = {}
RATE = 60  # requests per minute per key


def partner_key(x_api_key: str | None = Header(default=None)) -> str:
    keys = {k.strip() for k in os.environ.get("RADAR_PARTNER_KEYS", "").split(",") if k.strip()}
    if not keys or x_api_key not in keys:
        raise HTTPException(401, "brak lub zły nagłówek X-API-Key")
    tokens, at = _BUCKETS.get(x_api_key, [RATE, time.monotonic()])
    now = time.monotonic()
    tokens = min(RATE, tokens + (now - at) * RATE / 60)
    if tokens < 1:
        raise HTTPException(429, "limit 60 zapytań na minutę", headers={"Retry-After": "2"})
    _BUCKETS[x_api_key] = [tokens - 1, now]
    return x_api_key


@v1.get("/ideas", dependencies=[Depends(partner_key)])
def v1_ideas(q: str | None = None, sector: str | None = None, voivodeship: str | None = None, maturity: str | None = None,
             limit: int = 50, offset: int = 0):
    """Classified ideas with labels and score (same filters as the UI)."""
    from radar.api.explore import ideas

    return ideas(q=q, sector=sector, voivodeship=voivodeship, maturity=maturity, limit=min(limit, 200), offset=offset)


@v1.get("/match", dependencies=[Depends(partner_key)])
def v1_match(role: str = "inwestorzy", voivodeship: str | None = None, sectors: str | None = None, budget: str = "wysoki",
             goal: str = "zysk", limit: int = 20):
    """Explainable match of ideas to a profile."""
    from radar.api.explore import match

    return match(role=role, voivodeship=voivodeship, sectors=sectors, budget=budget, goal=goal,
                 stage="tech_ready" if goal == "zysk" else "exploring", limit=limit)


@v1.get("/cards/{card_id}", dependencies=[Depends(partner_key)])
def v1_card(card_id: int):
    """Full card with business case and investor signals."""
    from radar.api.main import card

    return card(card_id)
