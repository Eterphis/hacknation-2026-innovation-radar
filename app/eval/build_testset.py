"""Build eval/basal_gold.jsonl: gold labels for 60 real records (32 NCBR success stories, 28 Interreg 2021-2027 projects),
drawn with a fixed seed from the team harvester output (data/normalized/*.jsonl, radar.record/v1), with gold
labels assigned by hand (annotator: Claude, 2026-11-21, to be spot-checked by the team).

Labelling rules (same policy Basal implements, D-008):
  decision  accept = a concrete solution/result from or with a Polish public institution (school, university,
                     research institute, JST, other public body);
            reject = only private companies, no description of a solution, or not an innovation (plain works);
            hold   = public character unclear (NGOs / associations only) — the operator decides.
  sector    PKD-like section from radar/basal/taxonomy.py; "A|B" = two sections equally defensible (lenient score).
  institution_type  main Polish organisation; "a|b" = consortium with several public types.

Only ids, URLs and labels are committed: the record text stays in data/ (gitignored, source content licence
not cleared). `radar basal-eval` joins the labels with data/normalized/*.jsonl by record_id.

    python eval/build_testset.py <dir with ncbr.jsonl and interreg.jsonl>
"""
import json
import random
import sys
from pathlib import Path

GOLD = {  # index in draw order: (sector, decision, institution_type, note)
    0: ("P_edukacja", "accept", "uczelnia", ""), 1: ("Q_zdrowie|J_ict", "reject", "firma", "firma, brak opisu"),
    2: ("C_przemysl", "reject", "firma", ""), 3: ("P_edukacja", "accept", "uczelnia", ""),
    4: ("M_nauka", "accept", "uczelnia", ""), 5: ("A_rolnictwo", "reject", "firma", "konsorcjum firm"),
    6: ("P_edukacja", "accept", "uczelnia", ""), 7: ("P_edukacja", "accept", "uczelnia", ""),
    8: ("Q_zdrowie", "accept", "inna_publiczna", "szpital"), 9: ("Q_zdrowie", "accept", "inna_publiczna", "szpital"),
    10: ("D_energetyka", "accept", "instytut", ""), 11: ("M_nauka", "accept", "uczelnia", ""),
    12: ("M_nauka", "accept", "uczelnia|instytut", "obronność"), 13: ("C_przemysl", "accept", "instytut|uczelnia", ""),
    14: ("H_transport|Q_zdrowie", "accept", "instytut|uczelnia", ""), 15: ("A_rolnictwo", "accept", "instytut", ""),
    16: ("P_edukacja", "accept", "uczelnia", ""), 17: ("M_nauka", "accept", "uczelnia", ""),
    18: ("J_ict", "reject", "firma", ""), 19: ("P_edukacja|M_nauka", "accept", "uczelnia", ""),
    20: ("P_edukacja", "accept", "uczelnia", ""), 21: ("J_ict", "reject", "firma", ""),
    22: ("P_edukacja", "accept", "uczelnia", ""), 23: ("C_przemysl|F_budownictwo", "accept", "uczelnia", ""),
    24: ("P_edukacja", "accept", "uczelnia", ""), 25: ("F_budownictwo", "accept", "jst|uczelnia", ""),
    26: ("Q_zdrowie|P_edukacja", "reject", "firma", ""), 27: ("A_rolnictwo", "reject", "firma", "jednoosobowa firma"),
    28: ("D_energetyka|C_przemysl", "reject", "firma", ""), 29: ("P_edukacja", "accept", "uczelnia", ""),
    30: ("Q_zdrowie|M_nauka", "reject", "firma", ""), 31: ("Q_zdrowie|M_nauka", "accept", "uczelnia", ""),
    32: ("E_srodowisko|R_kultura", "accept", "jst", ""), 33: ("R_kultura", "accept", "uczelnia|inna_publiczna", "opis po niemiecku"),
    34: ("D_energetyka|A_rolnictwo", "accept", "uczelnia", ""), 35: ("H_transport", "reject", "jst", "inwestycja drogowa, nie innowacja"),
    36: ("E_srodowisko|O_administracja", "accept", "inna_publiczna|jst", ""), 37: ("H_transport", "accept", "jst", ""),
    38: ("R_kultura", "accept", "jst", ""), 39: ("R_kultura", "hold", "unknown", "tylko fundacja"),
    40: ("O_administracja|E_srodowisko", "accept", "inna_publiczna", "straż pożarna"), 41: ("R_kultura", "accept", "jst", ""),
    42: ("R_kultura", "accept", "uczelnia|jst", ""), 43: ("E_srodowisko|A_rolnictwo", "accept", "uczelnia|inna_publiczna", ""),
    44: ("Q_zdrowie", "accept", "inna_publiczna", ""), 45: ("P_edukacja", "accept", "jst|unknown", "euroregion, opis po niemiecku"),
    46: ("E_srodowisko", "accept", "jst|uczelnia", ""), 47: ("R_kultura", "accept", "jst", "opis po słowacku"),
    48: ("Q_zdrowie", "accept", "jst", ""), 49: ("E_srodowisko", "accept", "jst|uczelnia", ""),
    50: ("M_nauka|P_edukacja", "accept", "instytut|uczelnia", ""), 51: ("D_energetyka|O_administracja", "hold", "unknown", "tylko stowarzyszenia"),
    52: ("R_kultura", "accept", "jst", ""), 53: ("Q_zdrowie", "accept", "inna_publiczna", ""),
    54: ("E_srodowisko", "accept", "jst", ""), 55: ("R_kultura", "accept", "jst", ""),
    56: ("R_kultura", "accept", "jst", "opis po słowacku"), 57: ("O_administracja|E_srodowisko", "accept", "jst", "opis po słowacku"),
    58: ("O_administracja", "accept", "inna_publiczna", "policja"), 59: ("R_kultura|O_administracja", "accept", "jst|inna_publiczna|unknown", "EUWT"),
}


def main(src: str) -> None:
    out, i = [], 0
    for name, n, kind in (("ncbr", 32, "solution"), ("interreg", 28, "project")):
        rows = [json.loads(l) for l in open(Path(src) / f"{name}.jsonl", encoding="utf-8")]
        random.Random(2026).shuffle(rows)
        for r in rows[:n]:
            sector, decision, inst, note = GOLD[i]
            out.append({"i": i, "file": name, "kind": kind, "record_id": r["record_id"], "content_hash": r.get("content_hash"),
                        "url": r.get("url") or r.get("list_url"), "title": r.get("title", "")[:120],
                        "gold": {"sector": sector, "decision": decision, "institution_type": inst}, "note": note})
            i += 1
    dst = Path(__file__).with_name("basal_gold.jsonl")
    dst.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out), encoding="utf-8")
    print(f"{len(out)} records -> {dst}")


if __name__ == "__main__":
    main(sys.argv[1])
