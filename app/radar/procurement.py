"""Public procurement dossier for one idea ("teczka zamówienia publicznego"), by transparent rules, no LLM.

A municipality that wants a solution it saw in the radar needs four things before it can ask for offers: a
description of what it buys, how offers will be scored, the estimated value and the procedure the value implies,
and who could bid. Everything here is assembled from fields the pipeline already computed (the card, the business
case from `radar.business`, implementers from `radar.investor`): no new facts. The only rules added are the legal
thresholds and a sector -> CPV division mapping, each with its source and date.

Thresholds (Prawo zamówień publicznych, Dz.U. 2024 poz. 1320 as amended by Dz.U. 2025 poz. 1173):
- below 170 000 zł net (art. 2 ust. 1 pkt 1, from 1.01.2026; 130 000 zł until 31.12.2025): outside the act,
  internal rules of the contracting authority (rozeznanie rynku / zapytanie ofertowe);
- from 170 000 zł up to the EU threshold: tryb podstawowy (art. 275);
- from the EU threshold: przetarg nieograniczony (art. 132) or ograniczony.
EU threshold for supplies and services of contracting authorities other than central government, 2026-2027:
216 000 EUR = 930 960 zł at 4,31 zł/EUR (obwieszczenie Prezesa UZP z 8.12.2025, M.P. 2025 poz. 1288).
"""

from __future__ import annotations

import html
from datetime import date

NATIONAL_THRESHOLD_PLN = 170_000
EU_THRESHOLD_EUR = 216_000
EUR_PLN = 4.31
EU_THRESHOLD_PLN = round(EU_THRESHOLD_EUR * EUR_PLN)  # 930 960 zł
THRESHOLDS_SOURCE = ("art. 2 ust. 1 pkt 1 Pzp (170 000 zł od 1.01.2026, Dz.U. 2025 poz. 1173); "
                     "obwieszczenie Prezesa UZP z 8.12.2025 (216 000 EUR = 930 960 zł, kurs 4,31 zł)")
THRESHOLDS_AS_OF = "2026-01-01"

# Basal sector -> CPV division (Wspólny Słownik Zamówień, rozporządzenie 213/2008). A starting point for the
# contracting authority, labelled "do weryfikacji" in the output.
CPV = {
    "A_rolnictwo": ("77000000-0", "Usługi rolnicze, leśne, ogrodnicze, hodowlane i pszczelarskie"),
    "C_przemysl": ("42000000-6", "Maszyny przemysłowe"),
    "D_energetyka": ("09300000-2", "Energia elektryczna, cieplna, słoneczna i jądrowa"),
    "E_srodowisko": ("90000000-7", "Usługi odbioru ścieków, usuwania odpadów, czyszczenia i usługi ekologiczne"),
    "F_budownictwo": ("45000000-7", "Roboty budowlane"),
    "H_transport": ("60000000-8", "Usługi transportowe (z wyłączeniem transportu odpadów)"),
    "J_ict": ("72000000-5", "Usługi informatyczne: konsultacyjne, opracowywania oprogramowania, internetowe i wsparcia"),
    "M_nauka": ("73000000-2", "Usługi badawcze i eksperymentalno-rozwojowe oraz pokrewne usługi doradcze"),
    "O_administracja": ("79400000-8", "Usługi doradcze w zakresie działalności gospodarczej i zarządzania"),
    "P_edukacja": ("80000000-4", "Usługi edukacyjne i szkoleniowe"),
    "Q_zdrowie": ("85000000-9", "Usługi w zakresie zdrowia i opieki społecznej"),
    "R_kultura": ("92000000-1", "Usługi rekreacyjne, kulturalne i sportowe"),
}
CPV_DEFAULT = ("79400000-8", "Usługi doradcze w zakresie działalności gospodarczej i zarządzania")

# Offer criteria (weights in %). Art. 246 ust. 2 Pzp: a public-finance entity may weigh price above 60% only if it
# defines quality standards, so price never exceeds 60 here.
CRITERIA = {
    "standard": {"cena": 60, "jakość": 30, "czas wdrożenia": 10},
    "innowacja": {"cena": 40, "jakość": 40, "czas wdrożenia": 20},
}
QUALITY_HINTS = {
    "technologiczna": ["parametry techniczne potwierdzone testem / pilotażem", "gwarancja i serwis (miesiące)",
                       "zgodność z normami i interoperacyjność (otwarte formaty, API)"],
    "default": ["doświadczenie we wdrożeniu podobnego rozwiązania w innej instytucji", "plan szkolenia personelu",
                "wskaźniki rezultatu mierzone po 12 miesiącach"],
}


def procedure(value_pln: float, maturity: str | None) -> dict:
    """Procedure implied by the estimated net value; innovative routes are added for ideas not yet on the market."""
    v = float(value_pln or 0)
    if v < NATIONAL_THRESHOLD_PLN:
        mode, basis = "poza ustawą Pzp: rozeznanie rynku / zapytanie ofertowe", "art. 2 ust. 1 pkt 1 Pzp"
        note = ("przy dofinansowaniu z funduszy UE sprawdź zasadę konkurencyjności z wytycznych programu")
    elif v < EU_THRESHOLD_PLN:
        mode, basis = "tryb podstawowy", "art. 275 Pzp"
        note = "ogłoszenie w Biuletynie Zamówień Publicznych"
    else:
        mode, basis = "przetarg nieograniczony", "art. 132 Pzp"
        note = "ogłoszenie w Dzienniku Urzędowym UE"
    alternatives = []
    if maturity in ("exploring", "tech_ready"):
        alternatives.append({"mode": "partnerstwo innowacyjne", "basis": "art. 297 Pzp",
                             "why": "rozwiązanie nie jest jeszcze dostępne na rynku; zamawiający kupuje opracowanie i wdrożenie"})
        alternatives.append({"mode": "zamówienie przedkomercyjne (PCP)", "basis": "usługi B+R wyłączone z Pzp (art. 11 ust. 5 pkt 1)",
                             "why": "etap badań i prototypu; konkurencja kilku wykonawców na etapach"})
    return {"mode": mode, "basis": basis, "note": note, "value_pln": round(v),
            "thresholds": {"national_pln": NATIONAL_THRESHOLD_PLN, "eu_pln": EU_THRESHOLD_PLN, "eu_eur": EU_THRESHOLD_EUR,
                           "eur_pln": EUR_PLN, "as_of": THRESHOLDS_AS_OF, "source": THRESHOLDS_SOURCE},
            "alternatives": alternatives}


def criteria(rec, card) -> dict:
    """Offer criteria: price at most 60%; ideas that are technological or not yet on the market weigh quality more."""
    innov = (rec.innovation_type == "technologiczna") or (card.maturity in ("exploring", "tech_ready"))
    kind = "innowacja" if innov else "standard"
    hints = QUALITY_HINTS["technologiczna" if rec.innovation_type == "technologiczna" else "default"]
    return {"profile": kind, "weights": dict(CRITERIA[kind]), "quality_subcriteria": list(hints),
            "basis": "art. 242 i 246 Pzp (cena maks. 60% dla jednostek sektora finansów publicznych bez standardów jakości)"}


def _clean(text: str | None, n: int = 600) -> str:
    return " ".join((text or "").split())[:n]


def dossier(rec, card, bc: dict, implementers: list[dict] | None = None) -> dict:
    """The whole dossier as data (the endpoint returns it as JSON or renders it for print)."""
    from radar.basal.classifier import label_pl

    cpv_code, cpv_name = CPV.get(rec.sector or "", CPV_DEFAULT)
    target = [str(t) for t in (card.target_users or [])][:5]
    subject = {
        "name": card.solution_name or rec.title or "Wdrożenie rozwiązania",
        "need": _clean(card.problem_solved),
        "scope": _clean(card.what_is_new or card.summary_pl),
        "users": target,
        "sector": label_pl("sector", rec.sector) if rec.sector else None,
        "cpv": {"code": cpv_code, "name": cpv_name, "note": "sugerowany dział CPV, do weryfikacji przez zamawiającego"},
        "reference": {"title": rec.title, "organisation": (rec.affiliations or [None])[0], "voivodeship": rec.voivodeship,
                      "source_id": rec.source_id, "url": rec.url},
    }
    value = bc["deploy_cost_pln"]
    impl = [{"name": (rec.affiliations or ["twórca rozwiązania"])[0], "voivodeship": rec.voivodeship, "role": "twórca"}]
    impl += [{"name": o["name"], "voivodeship": o.get("voivodeship"), "role": "dostawca w sektorze",
              "ready": o.get("ready"), "ideas": o.get("ideas")} for o in (implementers or [])]
    return {
        "version": "procurement/v1",
        "card_id": card.id,
        "subject": subject,
        "estimated_value": {"net_pln": value, "basis": "koszt wdrożenia u odbiorcy z business case (business/v1)",
                            "assumption": next((a for a in bc.get("assumptions", []) if a.startswith("koszt wdrożenia")), None),
                            "savings_vs_own_build_pln": bc.get("savings_per_adopter_pln"), "payback": bc.get("payback")},
        "criteria": criteria(rec, card),
        "procedure": procedure(value, card.maturity),
        "implementers": impl,
        "funding": [f["programme"] for f in bc.get("funding", [])],
        "generated": date.today().isoformat(),
        "disclaimer": "Teczka złożona automatycznie z danych publicznych i reguł (bez modelu językowego). "
                      "Opis przedmiotu zamówienia i wartość szacunkowa wymagają weryfikacji przez zamawiającego (art. 28-36 Pzp).",
    }


def _zl(n) -> str:
    return "—" if n is None else f"{round(float(n)):,} zł".replace(",", " ")


def render(d: dict, auto_print: bool = False) -> str:
    """Print version (same look as the memo in radar.api.deals); ?auto=1 opens the print dialog."""
    e = html.escape
    s, v, cr, p = d["subject"], d["estimated_value"], d["criteria"], d["procedure"]
    li = lambda xs: "".join(f"<li>{e(str(x))}</li>" for x in xs if x)  # noqa: E731
    weights = "".join(f"<tr><td>{e(k)}</td><td><b>{w}%</b></td></tr>" for k, w in cr["weights"].items())
    impl = "".join(f"<li>{e(o['name'])} — {e(o.get('voivodeship') or '—')} ({e(o['role'])})</li>" for o in d["implementers"])
    alts = "".join(f"<li><b>{e(a['mode'])}</b> ({e(a['basis'])}): {e(a['why'])}</li>" for a in p["alternatives"])
    ref = s["reference"]
    return f"""<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Teczka zamówienia — {e(s['name'][:60])}</title><style>
:root{{--bg:#F4EFE6;--paper:#FFFDF9;--ink:#1D1B18;--ink2:#55514A;--red:#BE1A34;--line:#E4DCCD}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
.page{{max-width:820px;margin:24px auto;background:var(--paper);padding:36px 44px;border-radius:18px;box-shadow:0 10px 30px rgba(60,40,20,.12)}}
header{{border-bottom:3px solid var(--red);padding-bottom:12px}} .brand{{font-weight:800;color:var(--red)}} h1{{font-size:22px;margin:10px 0 4px}}
.meta{{color:var(--ink2);font-size:13px}} h2{{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--red);margin:20px 0 6px}}
table{{border-collapse:collapse;font-size:13px}} td{{border-top:1px solid var(--line);padding:5px 12px 5px 0}} ul{{margin:4px 0;padding-left:18px}}
.k{{display:inline-block;background:var(--bg);border-radius:12px;padding:10px 14px;margin:8px 8px 0 0}} .k small{{display:block;color:var(--ink2);font-size:11px}}
.note{{color:var(--ink2);font-size:11px;margin-top:18px;border-top:1px solid var(--line);padding-top:8px}}
.bar{{max-width:820px;margin:16px auto 0;text-align:right}} .bar button{{font:600 13px system-ui;padding:8px 14px;border-radius:10px;border:0;background:var(--red);color:#fff;cursor:pointer}}
@media (max-width:640px){{.page{{padding:20px;margin:0;border-radius:0}}}}
@media print{{body{{background:#fff}}.bar{{display:none}}.page{{box-shadow:none;margin:0;padding:0;max-width:none}}@page{{margin:14mm}}}}
</style></head><body><div class="bar"><button onclick="print()">Zapisz PDF</button></div>
<article class="page"><header><div class="brand">Radar Innowacji · Teczka zamówienia publicznego</div><h1>{e(s['name'])}</h1>
<div class="meta">{e(s['sector'] or '—')} · karta #{d['card_id']} · {e(d['generated'])}</div></header>
<div><span class="k"><small>Szacunkowa wartość netto</small><b>{_zl(v['net_pln'])}</b></span><span class="k"><small>Tryb</small><b>{e(p['mode'])}</b></span>
<span class="k"><small>Oszczędność vs budowa od zera</small><b>{_zl(v['savings_vs_own_build_pln'])}</b></span></div>
<h2>Opis przedmiotu zamówienia</h2><p><b>Potrzeba:</b> {e(s['need'] or '—')}</p><p><b>Zakres:</b> {e(s['scope'] or '—')}</p>
{f"<p><b>Użytkownicy:</b> {e(', '.join(s['users']))}</p>" if s['users'] else ''}
<p><b>CPV:</b> {e(s['cpv']['code'])} {e(s['cpv']['name'])} <span class="meta">({e(s['cpv']['note'])})</span></p>
<p class="meta">Rozwiązanie referencyjne: {e(ref['title'] or '—')} · {e(ref['organisation'] or '—')} · {e(ref['voivodeship'] or '—')} · źródło {e(ref['source_id'])}</p>
<h2>Kryteria oceny ofert</h2><table>{weights}</table><p class="meta">Podkryteria jakości:</p><ul>{li(cr['quality_subcriteria'])}</ul><p class="meta">{e(cr['basis'])}</p>
<h2>Wartość i tryb</h2><ul><li>{e(v['basis'])}{(': ' + e(v['assumption'])) if v['assumption'] else ''}</li>
<li>{e(p['mode'])} ({e(p['basis'])}); {e(p['note'])}</li><li>progi: {_zl(p['thresholds']['national_pln'])} (krajowy), {_zl(p['thresholds']['eu_pln'])} (unijny, dostawy i usługi)</li></ul>
{f'<p class="meta">Możliwe tryby dla innowacji:</p><ul>{alts}</ul>' if alts else ''}
<h2>Potencjalni wykonawcy</h2><ul>{impl}</ul>
<h2>Finansowanie</h2><ul>{li(d['funding']) or '<li>—</li>'}</ul>
<div class="note">{e(d['disclaimer'])} Progi: {e(p['thresholds']['source'])}.</div>
</article>{'<script>addEventListener("load",()=>setTimeout(print,300))</script>' if auto_print else ''}</body></html>"""
