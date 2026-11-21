"""HTML to a flat list of text blocks, plus text cleanup shared by connectors."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser

BLOCK_TAGS = {"p", "li", "figcaption", "summary", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "blockquote"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
SKIP_TAGS = {"script", "style", "noscript", "template"}

# Characters seen on gov.pl pages that should not survive into records.
_REPLACE = {
    " ": " ",  # nbsp
    "​": "",  # zero-width space
    "‌": "",
    "‍": "",
    "﻿": "",
    "": "-",  # private-use bullet from Word paste
    "": "-",
}
_FOLD_EXTRA = str.maketrans({"ł": "l", "Ł": "L"})


def clean_text(text: str) -> str:
    """Unicode NFC, page junk removed, spaces collapsed, newlines kept (max one blank line)."""
    text = unicodedata.normalize("NFC", text)
    for bad, good in _REPLACE.items():
        text = text.replace(bad, good)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n")]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


def fold(text: str) -> str:
    """Lowercase ASCII form for matching labels: 'Słowa Kluczowe:' -> 'slowa kluczowe:'."""
    text = clean_text(text).translate(_FOLD_EXTRA)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass
class Block:
    """One unit of page text.

    kind: "text" (paragraph-like), "heading", "link", "group_start", "group_end".
    strong_only: the whole text sat inside <strong>/<b> (gov.pl uses that as a label).
    """

    kind: str
    text: str = ""
    tag: str = ""
    attrs: dict[str, str] = field(default_factory=dict)
    strong_only: bool = False
    href: str | None = None

    @property
    def classes(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())


class _BlockParser(HTMLParser):
    def __init__(self, group_tag: str | None) -> None:
        super().__init__(convert_charrefs=True)
        self.group_tag = group_tag
        self.blocks: list[Block] = []
        self._stack: list[dict] = []
        self._skip = 0
        self._strong = 0
        self._link: dict | None = None

    # text routing -------------------------------------------------------
    def _add_text(self, text: str) -> None:
        if self._link is not None:
            self._link["text"].append(text)
        if not self._stack:
            return
        top = self._stack[-1]
        top["parts"].append(text)
        visible = text.strip()
        if visible:
            top["total"] += len(visible)
            if self._strong:
                top["strong"] += len(visible)

    def _close_block(self) -> None:
        top = self._stack.pop()
        text = clean_text("".join(top["parts"]))
        if not text:
            return
        kind = "heading" if top["tag"] in HEADING_TAGS else "text"
        self.blocks.append(
            Block(
                kind=kind,
                text=text,
                tag=top["tag"],
                attrs=top["attrs"],
                strong_only=top["total"] > 0 and top["strong"] == top["total"],
            )
        )

    # HTMLParser hooks ---------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        a = {k: (v or "") for k, v in attrs}
        if tag == self.group_tag:
            while self._stack:
                self._close_block()
            self.blocks.append(Block(kind="group_start", tag=tag, attrs=a))
        elif tag in BLOCK_TAGS:
            self._stack.append({"tag": tag, "attrs": a, "parts": [], "total": 0, "strong": 0})
        elif tag in ("strong", "b"):
            self._strong += 1
        elif tag == "br":
            self._add_text("\n")
        elif tag == "a":
            self._link = {"href": a.get("href"), "text": []}

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br" and not self._skip:
            self._add_text("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag == self.group_tag:
            while self._stack:
                self._close_block()
            self.blocks.append(Block(kind="group_end", tag=tag))
        elif tag in BLOCK_TAGS:
            # close up to and including the matching block (tolerates sloppy nesting)
            for i in range(len(self._stack) - 1, -1, -1):
                if self._stack[i]["tag"] == tag:
                    while len(self._stack) > i:
                        self._close_block()
                    break
        elif tag in ("strong", "b"):
            self._strong = max(0, self._strong - 1)
        elif tag == "a" and self._link is not None:
            link, self._link = self._link, None
            self.blocks.append(Block(kind="link", text=clean_text("".join(link["text"])), href=link["href"]))

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._add_text(data)

    def close(self) -> None:
        super().close()
        while self._stack:
            self._close_block()


def html_blocks(html: str, group_tag: str | None = None) -> list[Block]:
    """Parse HTML into blocks in document order. `group_tag` (e.g. "details") emits group markers."""
    parser = _BlockParser(group_tag)
    parser.feed(html)
    parser.close()
    return parser.blocks


def slice_element(html: str, tag: str) -> str | None:
    """First <tag ...>...</tag> fragment (non-nested tags like <article>, <main>)."""
    m = re.search(rf"<{tag}\b.*?</{tag}>", html, re.S | re.I)
    return m.group(0) if m else None
