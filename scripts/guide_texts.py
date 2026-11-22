"""Prepare the guides' narrations in advance (operator, offline) and list them for voice recording.

    python scripts/guide_texts.py http://localhost:8088 [per_persona]

For the top cards of every audience, asks the API once for the matching guide's narration with the local Bielik
(llm=1&fresh=1, operator action; validated, rule text when rejected). The text is stored in the card, so users only
ever read the stored version. Writes app/radar/api/static/audio/todo.json: the texts that still need a recording
(id, guide, text, sha). Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8088").rstrip("/")
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3
GUIDE_FOR = {"inwestorzy": "ada", "samorzady": "tomek", "startupy": "tomek", "szkoly": "ola", "uczelnie": "profesor", "innowatorzy": "radek"}
AUDIO = Path(__file__).resolve().parents[1] / "app" / "radar" / "api" / "static" / "audio"
HDR = {"X-Operator-Token": os.environ.get("RADAR_OPERATOR_TOKEN", "")}


def get(path):
    with urllib.request.urlopen(urllib.request.Request(BASE + path, headers=HDR), timeout=300) as r:
        return json.load(r)


def sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


index = json.loads((AUDIO / "index.json").read_text(encoding="utf-8")) if (AUDIO / "index.json").exists() else {}
todo, seen = [], set()
for persona, guide in GUIDE_FOR.items():
    taken = 0
    for it in get(f"/api/personas/{persona}?limit={N + 3}")["items"]:
        if it["card_id"] in seen:
            continue
        seen.add(it["card_id"])
        p = get(f"/api/cards/{it['card_id']}/pitch?guide={guide}")
        if p["by"] == "reguły" and not p.get("model_tried"):
            p = get(f"/api/cards/{it['card_id']}/pitch?guide={guide}&llm=1&fresh=1")
        key = f"{it['card_id']}-{guide}"
        if index.get(key, {}).get("sha") != sha(p["text"]):
            todo.append({"key": key, "guide": guide, "by": p["by"], "text": p["text"], "sha": sha(p["text"])})
        print(f"{p['by']:12} {key:12} {len(p['text']):4} zn.  {it['title'][:60]}")
        taken += 1
        if taken >= N:
            break
AUDIO.mkdir(parents=True, exist_ok=True)
(AUDIO / "todo.json").write_text(json.dumps(todo, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{len(todo)} do nagrania, {sum(len(t['text']) for t in todo)} znaków -> {AUDIO / 'todo.json'}")
