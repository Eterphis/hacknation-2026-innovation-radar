"""Page -> main text, metadata, links (rules only, no LLM).

Main text: blocks inside <article>/<main>/[role=main] when they hold enough text, otherwise every block
outside boilerplate (nav, header, footer, aside, forms, cookie banners, menus, share bars). Blocks that
are mostly link text (menus, tag clouds) are dropped. Metadata from <title>, meta/OpenGraph, JSON-LD and
<time>. PDF text via the optional `pypdf` package.
"""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from ..text import clean_text

BLOCK_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "blockquote", "dd", "dt", "figcaption",
              "pre", "div", "section", "article", "main", "header", "footer", "ul", "ol", "table", "tr", "br", "address"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "iframe", "canvas", "select", "button", "option"}
BOILER_TAGS = {"nav", "header", "footer", "aside", "form", "dialog"}
BOILER_ATTR = re.compile(r"(^|[\s_-])(cookie|cookies|rodo|gdpr|consent|menu|navbar|nav|breadcrumbs?|footer|header|"
                         r"sidebar|share|sharing|social|newsletter|banner|modal|popup|skip|pagination|related|"
                         r"comments?|widget|search|lang|language|accessibility|wcag)([\s_-]|$)", re.I)
# inside <article>/<main> only these mark boilerplate (an article's own <header> holds its title and date)
STRONG_BOILER = re.compile(r"(^|[\s_-])(cookie|cookies|rodo|gdpr|consent|breadcrumbs?|share|sharing|social|newsletter|"
                           r"pagination|related|comments?|tags?)([\s_-]|$)", re.I)
MAIN_TAGS = {"article", "main"}
VOID = {"br", "img", "hr", "input", "meta", "link", "source", "area", "base", "col", "embed", "param", "track", "wbr"}
DATE_RE = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2}|19\d{2})\b|\b(20\d{2}|19\d{2})-(\d{2})-(\d{2})\b")


@dataclass
class TextBlock:
    text: str
    tag: str
    in_main: bool
    link_chars: int = 0

    @property
    def is_heading(self) -> bool:
        return self.tag in HEADINGS


@dataclass
class Page:
    url: str
    title: str = ""
    h1: str = ""
    lang: str | None = None
    meta: dict = field(default_factory=dict)       # name/property -> content
    jsonld: list = field(default_factory=list)
    times: list = field(default_factory=list)      # <time datetime>
    links: list = field(default_factory=list)      # (href, text)
    blocks: list = field(default_factory=list)     # main TextBlocks
    canonical: str | None = None
    noindex: bool = False
    kind: str = "html"

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks)

    @property
    def body_text(self) -> str:
        return "\n".join(b.text for b in self.blocks if not b.is_heading)

    def jsonld_items(self) -> list[dict]:
        out = []

        def walk(x):
            if isinstance(x, dict):
                if "@graph" in x:
                    walk(x["@graph"])
                if x.get("@type"):
                    out.append(x)
            elif isinstance(x, list):
                for i in x:
                    walk(i)
        walk(self.jsonld)
        return out


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool, bool]] = []  # (tag, boiler, main)
        self.skip = 0
        self.buf: list[str] = []
        self.link_buf = 0
        self.cur_tag = "p"
        self.in_a: str | None = None
        self.a_text: list[str] = []
        self.in_title = False
        self.title: list[str] = []
        self.h1: list[str] = []
        self.in_h1 = False
        self.in_jsonld = False
        self.jsonld_buf: list[str] = []
        self.page = Page("")
        self.raw_blocks: list[TextBlock] = []

    @property
    def boiler(self) -> bool:
        return any(b for _, b, _ in self.stack)

    @property
    def main(self) -> bool:
        return any(m for _, _, m in self.stack)

    def flush(self) -> None:
        text = clean_text(" ".join(self.buf))
        if text and not self.boiler:
            self.raw_blocks.append(TextBlock(text, self.cur_tag, self.main, self.link_buf))
        self.buf, self.link_buf = [], 0

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "html" and a.get("lang"):
            self.page.lang = a["lang"].split("-")[0].lower()
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and a.get("content"):
                self.page.meta.setdefault(key, a["content"].strip())
            return
        if tag == "link" and "canonical" in a.get("rel", "").lower() and a.get("href"):
            self.page.canonical = a["href"]
            return
        if tag == "script" and "ld+json" in a.get("type", "").lower():
            self.in_jsonld = True
            self.jsonld_buf = []
            return
        if tag in SKIP_TAGS:
            self.skip += 1
            return
        if tag == "title":
            self.in_title = True
            return
        if tag == "time" and a.get("datetime"):
            self.page.times.append(a["datetime"])
        if tag == "a":
            self.in_a = a.get("href")
            self.a_text = []
        if tag in VOID:
            if tag == "br":
                self.buf.append("\n")
            return
        attr = " ".join((a.get("class", ""), a.get("id", ""), a.get("role", ""), a.get("aria-label", "")))
        hidden = a.get("aria-hidden") == "true" or "display:none" in a.get("style", "").replace(" ", "")
        if self.main:
            boiler = tag in {"nav", "aside", "form", "dialog"} or bool(STRONG_BOILER.search(attr)) or hidden
        else:
            boiler = tag in BOILER_TAGS or bool(BOILER_ATTR.search(attr)) or hidden
        main = tag in MAIN_TAGS or a.get("role") == "main" or a.get("itemprop") == "articleBody"
        if main and boiler and tag in MAIN_TAGS:
            boiler = False  # <main class="... header-offset"> is still main content
        if tag in BLOCK_TAGS:
            self.flush()
            self.cur_tag = tag
        if tag == "h1":
            self.in_h1 = True
        self.stack.append((tag, boiler, main))

    def handle_endtag(self, tag):
        if tag == "script" and self.in_jsonld:
            self.in_jsonld = False
            try:
                self.page.jsonld.append(json.loads("".join(self.jsonld_buf)))
            except (json.JSONDecodeError, ValueError):
                pass
            return
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if tag == "title":
            self.in_title = False
            return
        if tag == "a" and self.in_a is not None:
            self.page.links.append((self.in_a, clean_text(" ".join(self.a_text))))
            self.in_a = None
        if tag == "h1":
            self.in_h1 = False
        if tag in VOID:
            return
        # pop to the matching tag (tolerates unclosed children)
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                if tag in BLOCK_TAGS:
                    self.flush()
                    self.cur_tag = "p"
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.in_jsonld:
            self.jsonld_buf.append(data)
            return
        if self.skip:
            return
        if self.in_title:
            self.title.append(data)
            return
        if self.in_a is not None:
            self.a_text.append(data)
        if self.in_h1 and not self.boiler:
            self.h1.append(data)
        self.buf.append(data)
        if self.in_a is not None:
            self.link_buf += len(data.strip())


def _select_main(blocks: list[TextBlock]) -> list[TextBlock]:
    main = [b for b in blocks if b.in_main]
    chosen = main if sum(len(b.text) for b in main) >= 200 else blocks
    out, seen = [], set()
    for b in chosen:
        if len(b.text) < 2:
            continue
        if b.link_chars and b.link_chars / max(1, len(b.text)) > 0.6 and len(b.text) < 300:
            continue  # menus, tag clouds, "czytaj więcej"
        key = b.text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
    return out


def extract_html(html: str, url: str) -> Page:
    p = _Parser()
    try:
        p.feed(html)
        p.close()
    except Exception:  # broken markup: keep what was parsed
        pass
    p.flush()
    page = p.page
    page.url = url
    page.title = clean_text(" ".join(p.title))
    page.h1 = clean_text(" ".join(p.h1))
    page.blocks = _select_main(p.raw_blocks)
    robots = page.meta.get("robots", "").lower()
    page.noindex = "noindex" in robots
    return page


def extract_pdf(content: bytes, url: str) -> Page | None:
    """Text of a PDF as paragraph blocks; None when pypdf is not installed."""
    try:
        from pypdf import PdfReader  # optional dependency
    except ImportError:
        return None
    page = Page(url, kind="pdf")
    try:
        reader = PdfReader(io.BytesIO(content))
        info = reader.metadata or {}
        page.title = clean_text(str(info.get("/Title") or ""))
        if info.get("/CreationDate"):
            page.meta["pdf:created"] = str(info.get("/CreationDate"))
        texts = []
        for pg in reader.pages[:60]:
            texts.append(pg.extract_text() or "")
    except Exception:
        return page
    raw = "\n".join(texts)
    paras = [clean_text(x) for x in re.split(r"\n\s*\n|(?<=[.!?])\n(?=[A-ZŁŚŻŹĆŃÓĘĄ])", raw)]
    page.blocks = [TextBlock(t.replace("\n", " "), "p", True) for t in paras if len(t) > 1]
    if not page.title and page.blocks:
        page.title = page.blocks[0].text[:200]
    return page


# --- metadata helpers ------------------------------------------------------------
def _norm_date(raw: str | None) -> str | None:
    if not raw:
        return None
    m = re.search(r"(19|20)\d{2}-\d{2}-\d{2}", raw)
    if m:
        return m.group(0)
    m = re.search(r"D:((?:19|20)\d{2})(\d{2})(\d{2})", raw)  # PDF date
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = DATE_RE.search(raw)
    if m:
        if m.group(1):
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            y, mo, d = int(m.group(4)), int(m.group(5)), int(m.group(6))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


def published_date(page: Page) -> str | None:
    for item in page.jsonld_items():
        for k in ("datePublished", "dateCreated", "startDate"):
            d = _norm_date(str(item.get(k) or ""))
            if d:
                return d
    for k in ("article:published_time", "og:published_time", "datepublished", "date", "dc.date", "dcterms.date",
              "pdf:created"):
        d = _norm_date(page.meta.get(k))
        if d:
            return d
    for t in page.times:
        d = _norm_date(t)
        if d:
            return d
    head = " ".join(b.text for b in page.blocks[:6])
    return _norm_date(head)


def modified_date(page: Page) -> str | None:
    for item in page.jsonld_items():
        d = _norm_date(str(item.get("dateModified") or ""))
        if d:
            return d
    for k in ("article:modified_time", "og:updated_time", "datemodified", "last-modified"):
        d = _norm_date(page.meta.get(k))
        if d:
            return d
    return None


def best_title(page: Page, site_name: str = "") -> str:
    for cand in (page.meta.get("og:title"), page.h1, page.title):
        if not cand:
            continue
        t = clean_text(cand)
        # drop " | Site name" / " - Site name" suffixes
        parts = re.split(r"\s+[|–—-]\s+", t)
        if len(parts) > 1 and (not site_name or any(site_name.lower()[:12] in p.lower() for p in parts[1:])
                               or len(parts[-1]) < 40):
            t = parts[0] if len(parts[0]) >= 12 else t
        if len(t) >= 5:
            return t
    return ""


def description(page: Page) -> str:
    return clean_text(page.meta.get("og:description") or page.meta.get("description") or "")
