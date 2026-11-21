"""Page type and an innovation pre-filter from word lists (no LLM, no merit judgement).

The score only decides whether a crawled page becomes a record worth a human's or a later model's
time; it is stored with the matched terms so every decision can be explained.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..text import fold

# patterns run on folded text (lowercase, no Polish letters)
GROUPS: dict[str, list[str]] = {
    "innovation": [
        r"innowac", r"opracowal", r"opracowan", r"wdroz", r"prototyp", r"demonstrator", r"patent", r"wynalaz",
        r"nowa technologi|nowej technologii|nowych technologii", r"nowatorsk", r"komercjaliz", r"transfer technologii",
        r"licencj", r"spin[- ]?off|spolk\w* odpryskow", r"start-?up", r"\btrl\b", r"badan\w* i rozwoj|\bb\+r\b",
        r"know-how", r"sztuczn\w* inteligencj|\bai\b|uczeni\w* maszynow", r"automatyzac", r"cyfryzac|cyfrow\w* transformac",
        r"rozwiazani\w* (?:technologiczn|innowacyjn)", r"technologi\w* (?:wodorow|kwantow|laserow|biotechnolog|medyczn)",
    ],
    "project": [
        r"\bprojekt", r"dofinansowan", r"wartosc projektu|wartosc calkowita", r"beneficjent", r"okres realizacji",
        r"fundusz\w* europejsk|\bue\b|unii europejskiej", r"\bncbr\b|narodowe centrum badan i rozwoju", r"\bparp\b",
        r"\bncn\b|narodowe centrum nauki", r"horyzont europa|horizon", r"program\w* operacyjn|fundusze europejskie dla",
        r"\befrr\b|\befs\b", r"grant",
    ],
    "offer": [
        r"oferta technologiczn|oferty technologiczne", r"oferta wspolpracy", r"technologi\w* do komercjalizacji",
        r"zlecen\w* badawcz", r"uslug\w* badawcz", r"laboratorium akredytowan",
    ],
    "event": [r"konferencj", r"webinar", r"szkoleni", r"warsztat", r"\bzapisy\b|rejestracja uczestnikow", r"spotkani\w* informacyjn"],
    "negative": [
        r"polityka prywatnosci", r"regulamin", r"\bcookies?\b", r"rekrutacj", r"oferta pracy|oferty pracy|praca dla",
        r"przetarg|zamowieni\w* publiczn|zapytanie ofertowe", r"deklaracja dostepnosci", r"mapa strony", r"\bkontakt\b",
        r"nabor wnioskow|ogloszenie o naborze", r"wyniki wyborow|sesja rady",
    ],
}
COMPILED = {g: [re.compile(p) for p in pats] for g, pats in GROUPS.items()}
MIN_TEXT = 400


@dataclass
class Signals:
    hits: dict = field(default_factory=dict)   # group -> matched patterns (as written)
    score: float = 0.0
    page_type: str = "other"
    keep: bool = False
    reason: str = ""

    def to_json(self) -> dict:
        return {"hits": self.hits, "score": round(self.score, 2), "page_type": self.page_type}


def _hits(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for group, pats in COMPILED.items():
        found = [GROUPS[group][i] for i, p in enumerate(pats) if p.search(text)]
        if found:
            out[group] = found
    return out


def classify(title: str, body: str, *, published: str | None = None, keep_all: bool = False,
             min_score: float = 2.0, noindex: bool = False, kind: str = "html") -> Signals:
    t, b = fold(title or ""), fold(body or "")
    in_body, in_title = _hits(b), _hits(t)
    n = {g: len(set(in_body.get(g, [])) | set(in_title.get(g, []))) for g in GROUPS}
    title_bonus = 0.5 * len(in_title.get("innovation", [])) + 0.5 * len(in_title.get("offer", []))
    score = (n["innovation"] + 0.5 * min(n["project"], 4) + 1.5 * n["offer"] + title_bonus
             - 1.0 * len(in_title.get("negative", [])) - 0.3 * n["negative"] - 0.5 * min(n["event"], 2))
    if n["offer"]:
        page_type = "technology_offer"
    elif n["project"] >= 3:
        page_type = "project"
    elif n["event"] >= 2 and n["innovation"] < 2:
        page_type = "event"
    elif kind == "pdf":
        page_type = "document"
    elif published:
        page_type = "news"
    else:
        page_type = "other"
    hits = {g: sorted(set(in_body.get(g, [])) | set(in_title.get(g, []))) for g in GROUPS if n[g]}
    sig = Signals(hits, score, page_type)
    length = len(body or "")
    if noindex:
        sig.reason = "noindex"
    elif length < (300 if keep_all else MIN_TEXT):
        sig.reason = f"za mało tekstu ({length} znaków)"
    elif keep_all:
        sig.keep, sig.reason = True, "witryna z listą projektów (keep_all)"
    elif in_title.get("negative") and n["innovation"] < 2:
        sig.reason = "strona serwisowa (" + ", ".join(in_title["negative"]) + ")"
    elif score < min_score:
        sig.reason = f"za słabe sygnały innowacji (wynik {score:.1f} < {min_score})"
    else:
        sig.keep, sig.reason = True, f"sygnały innowacji (wynik {score:.1f})"
    return sig
