"""Innovation card: normalized record -> extraction -> maturity -> score -> path and recipients,
plus the justification for the official in the layout of an administrative decision (I-011).

Run:  python -m radar.card --in data/normalized/ncbr.jsonl --ids <record_id>,<record_id>
      RADAR_LLM=offline|claude|auto (default auto)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import assess
from .extract import PROMPT_VERSION, LLMError, run_extraction
from .llm import get_providers

CARD_SCHEMA = "radar.card/v1"
SOURCE_LABEL = {"ncbr_sukcesy": "NCBR"}


def build_card(record: dict, providers=None, now: str | None = None) -> dict:
    providers = providers if providers is not None else get_providers()
    reasons: list[str] = []
    if record.get("quality", {}).get("status") != "ok":
        reasons += [f"rekord źródłowy: {r}" for r in record["quality"].get("blocking", [])]
    try:
        ex = run_extraction(record, providers)
    except LLMError as e:
        return {"schema": CARD_SCHEMA, "card_id": _card_id(record), "record_id": record["record_id"],
                "title": record.get("title"), "status": "needs_review", "reasons": reasons + [str(e)]}

    data = ex.data
    mat = assess.maturity(data)
    scores = assess.score(record, data, mat)
    rt = assess.route(record, data, mat, scores)
    contra = assess.against(record, data, mat, scores)
    if ex.dropped:
        reasons.append("usunięto twierdzenia bez potwierdzenia w źródle: " + ", ".join(ex.dropped))
    if data.get("is_innovation") == "nie":
        reasons.append("ekstrakcja: opis nie przedstawia konkretnego rozwiązania")
    if not (data.get("problem_solved") or {}).get("value"):
        reasons.append("brak opisu problemu z cytatem")

    return {
        "schema": CARD_SCHEMA,
        "card_id": _card_id(record),
        "record_id": record["record_id"],
        "source": record.get("source"),
        "url": record.get("url"),
        "title": record.get("title"),
        "status": "needs_review" if reasons else "ready",
        "reasons": reasons,
        "facts": {
            "organizations": record.get("organizations", []),
            "people": [p for p in record.get("people", []) if p.get("role") == "beneficiary"],
            "region": record.get("region"),
            "period": record.get("period"),
            "funding": record.get("funding"),
            "keywords": record.get("keywords", []),
        },
        "extraction": data,
        "maturity": mat,
        "scores": scores,
        "route": rt,
        "against": contra,
        "limitations": [
            "Ocena wstępna, oparta wyłącznie na opisie z jednego źródła (NCBR, strona sukcesów: wybór sukcesów, nie pełna populacja).",
            "Status publiczny instytucji niepotwierdzony w rejestrze (RAD-on do podłączenia).",
            "Katalog konkretnych odbiorców (beneficjenci Kohesio, partnerzy Interreg) jeszcze niepodłączony: odbiorcy to typy instytucji.",
            "Patenty krajowe (UPRP) niedostępne automatycznie.",
        ],
        "provenance": {
            "extractor": ex.provider,
            "model": ex.model,
            "prompt_version": PROMPT_VERSION,
            "assess_version": assess.ASSESS_VERSION,
            "attempts": ex.attempts,
            "validation_errors_seen": ex.errors_seen,
            "fallback_reason": ex.fallback_reason,
            "record_content_hash": record.get("content_hash"),
            "created_at": now or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    }


def _card_id(record: dict) -> str:
    return "K-" + hashlib.sha1(f"{record.get('source')}:{record['record_id']}".encode()).hexdigest()[:8].upper()


# --- justification for the official --------------------------------------------
def _src(card: dict) -> str:
    return f"[{SOURCE_LABEL.get(card.get('source'), card.get('source'))}]({card.get('url')})"


def _q(text: str, n: int = 220) -> str:
    text = " ".join(text.split())
    return f"„{text if len(text) <= n else text[:n].rsplit(' ', 1)[0] + '…'}”"


def render_justification(card: dict) -> str:
    if "extraction" not in card:
        return f"# {card.get('title')}\n\nKarta niekompletna: {'; '.join(card.get('reasons', []))}\n"
    ex, mat, sc, rt, facts = card["extraction"], card["maturity"], card["scores"], card["route"], card["facts"]
    src = _src(card)
    orgs = [o for o in facts["organizations"] if o.get("role") == "beneficiary"]
    org_txt = "; ".join(o["name"] for o in orgs)
    if not org_txt:  # sole traders show up as "Firma Imię Nazwisko" and parse as a person
        named = [p["source_text"] for p in facts.get("people", []) if p.get("role") == "beneficiary"]
        org_txt = ("; ".join(named) + " (beneficjent wpisany z imienia i nazwiska, np. JDG)") if named else "nieustalona organizacja"
    region = ", ".join(facts["region"]["voivodeships"]) or "region nieustalony"
    period = facts["period"]
    fund = facts["funding"]
    L: list[str] = []
    L.append(f"# Uzasadnienie rekomendacji · karta {card['card_id']}")
    L.append(f"**{ex['solution_name']['value'] or card['title']}**  ")
    L.append(f"Status karty: `{card['status']}` · Ocena łączna: **{str(sc['total']).replace('.', ',')} / 5** "
             f"({sc['light_pl']}: {sc['verdict']})")
    if card["reasons"]:
        L.append(f"\n> Do przeglądu: {'; '.join(card['reasons'])}")

    L.append("\n## 1. Co ustalono (fakty i dowody)")
    L.append(f"- **Twórca:** {org_txt} (woj. {region}) {src}")
    if fund.get("contest") or fund.get("total_value"):
        amount = f"{fund['total_value']:,.2f} zł".replace(",", " ").replace(".", ",") if fund.get("total_value") else "kwota nieznana"
        L.append(f"- **Finansowanie:** {fund.get('programme') or ''} · konkurs {fund.get('contest') or '—'} · wartość {amount} {src}")
    if period.get("start"):
        status_pl = {"finished": "zakończony", "running": "w trakcie", "planned": "planowany"}.get(period.get("status"), "?")
        L.append(f"- **Okres realizacji:** {period['start']} – {period.get('end') or 'w toku'} ({status_pl}) {src}")
    if ex["problem_solved"]["value"]:
        L.append(f"- **Problem:** {_q(ex['problem_solved']['quote'])} {src}")
    if ex["what_is_new"]["value"]:
        L.append(f"- **Co nowego:** {_q(ex['what_is_new']['quote'])} {src}")
    if ex["requirements"]["value"]:
        L.append(f"- **Wymagania wdrożenia:** {_q(ex['requirements']['quote'])} {src}")
    for e in mat["evidence"]:
        L.append(f"- **Dowód dojrzałości ({e['label']}):** {_q(e['quote'])} {src}")
    if mat["hidden"]:
        L.append(f"- **Wniosek:** {mat['hidden_pl']}.")
    L.append(f"- **Typ innowacji:** {ex['innovation_type']}; dziedziny: {', '.join(ex['sectors']) or 'nieustalone'}")

    L.append("\n## 2. Według jakich kryteriów oceniono")
    L.append(" · ".join(c["label"] for c in sc["criteria"]) + f". Metoda: {sc['method']}.")

    L.append("\n## 3. Ocena")
    L.append("| Kryterium | Ocena | Uzasadnienie |\n|---|---|---|")
    for c in sc["criteria"]:
        L.append(f"| {c['label']} | {c['dots']} | {c['why']} |")
    L.append(f"\nDojrzałość: **{mat['level_pl']}**. Brakuje do następnego poziomu: {mat['missing']}.")

    L.append("\n## 4. Co przemawia przeciw")
    L += [f"- {a}" for a in card["against"]]

    L.append("\n## 5. Rozstrzygnięcie: do czego i dla kogo")
    L.append(f"- **Ścieżka:** {rt['path_pl']}")
    if rt["recipients"]:
        L.append("- **Odbiorcy:**")
        for r in rt["recipients"]:
            tag = ", sektor publiczny" if r["public_sector"] else ""
            distinct = r["reason"] and r["reason"].lower() not in r["label"].lower()
            who = f" ({r['reason']}{tag})" if distinct else (f" ({tag[2:]})" if tag else "")
            L.append(f"  - {r['label']}{who}: {_q(r['quote'], 160)} {src}")
    else:
        L.append("- **Odbiorcy:** źródło ich nie wymienia; do ustalenia z twórcą.")
    if rt["pci_priority_sectors"]:
        L.append(f"- **Zgodność ze specjalizacjami PCI:** {', '.join(rt['pci_priority_sectors'])}")
    L.append("- **Mierniki skuteczności:** " + "; ".join(rt["metrics"]))

    L.append("\n## 6. Ograniczenia")
    L += [f"- {x}" for x in card["limitations"]]
    p = card["provenance"]
    L.append(f"\n<sub>Ekstrakcja: {p['extractor']}{' (' + p['model'] + ')' if p['model'] else ''}, "
             f"{p['prompt_version']}, prób: {p['attempts']}"
             f"{', zapas: ' + p['fallback_reason'] if p['fallback_reason'] else ''}. "
             f"Ocena: {p['assess_version']}. Utworzono: {p['created_at']}.</sub>")
    return "\n".join(L) + "\n"


# --- CLI -----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default="data/normalized/ncbr.jsonl")
    ap.add_argument("--ids", default=None, help="comma-separated record_id list (default: all ok records)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--llm", default=None, help="auto | claude | offline (overrides RADAR_LLM)")
    ap.add_argument("--out", default="data/cards", help="directory for cards.jsonl and <card_id>.md")
    args = ap.parse_args(argv)

    records = [json.loads(line) for line in Path(args.inp).read_text("utf-8").splitlines() if line.strip()]
    if args.ids:
        wanted = [i.strip() for i in args.ids.split(",") if i.strip()]
        by_id = {r["record_id"]: r for r in records}
        missing = [i for i in wanted if i not in by_id]
        if missing:
            print(f"unknown record_id: {', '.join(missing)}", file=sys.stderr)
            return 2
        records = [by_id[i] for i in wanted]
    else:
        records = [r for r in records if r.get("quality", {}).get("status") == "ok"]
    if args.limit:
        records = records[: args.limit]

    providers = get_providers(args.llm)
    print(f"extractors: {' -> '.join(p.name for p in providers)}", file=sys.stderr)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with (out / "cards.jsonl").open("w", encoding="utf-8") as fh:
        for i, rec in enumerate(records, 1):
            card = build_card(rec, providers)
            fh.write(json.dumps(card, ensure_ascii=False) + "\n")
            (out / f"{card['card_id']}.md").write_text(render_justification(card), "utf-8")
            counts[card["status"]] = counts.get(card["status"], 0) + 1
            light = card.get("scores", {}).get("light", "-")
            total = card.get("scores", {}).get("total", "-")
            print(f"[{i}/{len(records)}] {card['card_id']} {card['status']:<12} {total!s:>4} {light:<8} {card['title'][:70]}",
                  file=sys.stderr)
    print(f"cards: {counts} -> {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
