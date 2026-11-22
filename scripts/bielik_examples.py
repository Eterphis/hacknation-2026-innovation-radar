"""Generate guide narrations with the local small model for a few top cards and write a side-by-side report.

    python scripts/bielik_examples.py http://localhost:8088 [n]

Needs the API started with RADAR_LOCAL_LLM_URL pointing at a llama.cpp server running Bielik 1.5B. Each narration
is generated once and cached in the card (later calls are instant). Writes docs/bielik-przyklady.md.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8088").rstrip("/")
N = int(sys.argv[2]) if len(sys.argv) > 2 else 6
GUIDE_FOR = {"inwestorzy": "ada", "samorzady": "tomek", "szkoly": "ola", "uczelnie": "profesor", "innowatorzy": "radek", "startupy": "tomek"}


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=300) as r:
        return json.load(r)


rows, picked = [], set()
for persona, guide in GUIDE_FOR.items():
    for it in get(f"/api/personas/{persona}?limit=5")["items"]:
        if it["card_id"] in picked:
            continue
        picked.add(it["card_id"])
        t0 = time.time()
        p = get(f"/api/cards/{it['card_id']}/pitch?guide={guide}&fresh=1&llm=1")
        rows.append({"title": it["title"], "card_id": it["card_id"], "guide": guide, "by": p["by"], "seconds": p.get("seconds") or round(time.time() - t0, 1),
                     "rules": p.get("rules") or p["text"], "text": p["text"]})
        print(f"{p['by']:12} {rows[-1]['seconds']:6} s  {guide:9} {it['title'][:70]}")
        break
    if len(rows) >= N:
        break

ok = sum(r["by"] != "reguły" for r in rows)
lines = ["# Bielik 1.5B: przykłady narracji przewodników", "",
         f"Wygenerowane {time.strftime('%Y-%m-%d %H:%M')} lokalnie: Bielik-1.5B-v3.0-Instruct GGUF Q8_0 w llama.cpp, 4 vCPU, bez GPU.",
         f"Tekst modelu przyjęty w {ok} z {len(rows)} przypadków; pozostałe odrzuciła walidacja (nowa liczba, zła długość, niedokończone zdanie) i został tekst z reguł.",
         f"Średni czas generowania: {sum(r['seconds'] for r in rows) / max(1, len(rows)):.1f} s na narrację (raz na kartę i przewodnika, potem z pamięci).", "",
         "## Wnioski", "",
         "- 1.5B na CPU (~18 tokenów/s na 4 vCPU) dobrze **streszcza i wygładza** listę faktów w 2–3 zdania mówione; gotowy tekst do przepisania tylko kopiuje, więc dostaje fakty punktami, bez tytułu.",
         "- Walidacja odrzuca każdą liczbę spoza faktów i ucięte zdania; wtedy zostaje tekst z reguł. **Nie łapie przekręconego sensu** (zdarza się, np. zamiana słowa w opisie problemu), dlatego narracja jest oznaczona w UI jako „Bielik 1.5B”, a fakty z karty są obok.",
         "- Koszt: zero zł za token; jedna narracja raz na kartę i przewodnika, potem z pamięci w karcie. Dla 1000 nowych kart × 5 przewodników ≈ 10 h CPU w tle albo tylko dla otwieranych kart.",
         "- Lepsza jakość: Bielik 4.5B / 11B (GGUF, 6–12 GB RAM) bez zmian w kodzie (`RADAR_LOCAL_GGUF`).", ""]
for r in rows:
    lines += [f"## {r['title']}", f"Przewodnik: **{r['guide']}** · źródło tekstu: **{r['by']}** · {r['seconds']} s · karta `#{r['card_id']}`", "",
              "**Fakty (reguły):**", "", "> " + r["rules"], "", "**Narracja:**", "", "> " + r["text"], ""]
out = Path(__file__).resolve().parents[1] / "docs" / "bielik-przyklady.md"
out.write_text("\n".join(lines), encoding="utf-8")
print("wrote", out)
