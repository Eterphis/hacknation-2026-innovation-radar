"""Turn a narration into text a voice reads well: no slashes, ranges or abbreviations (used before recording)."""

from __future__ import annotations

import re
import sys

RULES = [
    (r"\b(\d+)/100\b", r"\1 na 100"),
    (r"\b(?:w ciągu|już po|po|w) 1-2 lat\w*", "w ciągu roku lub dwóch lat"),
    (r"\b1-2 lat\w*", "rok lub dwa lata"),
    (r"\b(\d+)-(\d+)\b", r"od \1 do \2"),
    (r"\bwoj\.\s*", "województwo "),
    (r"\bim\. ", "imienia "),
    (r"\bmln zł\b", "milionów złotych"),
    (r"\bmld zł\b", "miliardów złotych"),
    (r"\btys\. zł\b", "tysięcy złotych"),
    (r"\bzł\b", "złotych"),
    (r"(\d+)%", r"\1 procent"),
    (r"(\d+,\d+) milionów", r"\1 miliona"),
    (r"\b(\d{2})(\d{3})\b", r"\1 \2"),
    (r"\bsp\. z o\.o\.?", "spółka z o.o."),
    (r"\s*\(([^)]*)\)", r", \1,"),
    (r"/", " lub "),
    (r",\s*,", ","), (r",\s*\.", "."), (r"\s+", " "),
]


def speech(text: str) -> str:
    for a, b in RULES:
        text = re.sub(a, b, text)
    return text.strip()


if __name__ == "__main__":
    print(speech(sys.stdin.read()))
