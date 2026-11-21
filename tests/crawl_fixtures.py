"""Shared HTML fixtures and a fake HTTP opener for the crawler tests (no network)."""
import io
import urllib.error
from email.message import Message

from radar.crawl.sites import Site

ARTICLE = """<!doctype html>
<html lang="pl-PL"><head>
<title>Czujnik wilgotności gleby z AI | Centrum Transferu Technologii PRz</title>
<meta name="description" content="Naukowcy opracowali prototyp czujnika wilgotności gleby.">
<meta property="og:title" content="Czujnik wilgotności gleby z AI – Centrum Transferu Technologii PRz">
<meta name="keywords" content="rolnictwo precyzyjne, czujniki; sztuczna inteligencja">
<link rel="canonical" href="https://ctt.example.pl/aktualnosci/czujnik-gleby">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"NewsArticle",
 "headline":"Czujnik wilgotności gleby z AI","datePublished":"2026-03-14T09:00:00+01:00",
 "dateModified":"2026-03-20"}</script>
</head><body>
<div class="cookie-banner"><p>Ta strona używa plików cookies. Polityka prywatności i regulamin.</p></div>
<header><nav><ul><li><a href="/">Start</a></li><li><a href="/oferta">Oferta</a></li>
<li><a href="/kontakt">Kontakt</a></li></ul></nav></header>
<main><article>
<h1>Czujnik wilgotności gleby z AI</h1>
<p>Zespół Politechniki Rzeszowskiej opracował prototyp czujnika wilgotności gleby, który dzięki
sztucznej inteligencji przewiduje zapotrzebowanie upraw na wodę. Rozwiązanie technologiczne zostało
zgłoszone do ochrony patentowej, a uczelnia szuka partnera do komercjalizacji i wdrożenia w gospodarstwach
województwa podkarpackiego.</p>
<p>Projekt był realizowany przy współpracy z firmą AgroSensor Sp. z o.o. i otrzymał dofinansowanie
z Narodowego Centrum Badań i Rozwoju. Okres realizacji: 01.2024 – 12.2025. Wartość projektu: 1 200 000 zł.
Prototyp przeszedł testy polowe na poziomie TRL 6, a transfer technologii ma objąć licencję dla producenta.</p>
<p><a href="/aktualnosci/inny-wpis?utm_source=x">Inny wpis</a> oraz <a href="https://inna-domena.pl/x">link zewnętrzny</a>
i <a href="/pliki/raport.pdf">raport w PDF</a>.</p>
</article></main>
<footer><p>Politechnika Rzeszowska, al. Powstańców Warszawy 12, 35-959 Rzeszów. Deklaracja dostępności.</p></footer>
</body></html>"""

PRIVACY = """<html><head><title>Polityka prywatności</title></head><body><main>
<h1>Polityka prywatności</h1>
<p>""" + ("Administratorem danych osobowych jest uczelnia. Dane przetwarzamy zgodnie z RODO. " * 12) + """</p>
</main></body></html>"""

EMPTY = "<html><head><title>Pusta</title></head><body><nav><a href='/'>Start</a></nav></body></html>"

LIST = """<html><head><title>Aktualności</title></head><body><main>
<h1>Aktualności</h1>
<ul><li><a href="/aktualnosci/czujnik-gleby">Czujnik wilgotności gleby z AI</a></li>
<li><a href="/aktualnosci/polityka">Polityka prywatności</a></li>
<li><a href="/aktualnosci/zniknie">Wpis, który zniknie</a></li></ul>
</main></body></html>"""

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://ctt.example.pl/aktualnosci/czujnik-gleby</loc><lastmod>2026-03-20</lastmod></url>
<url><loc>https://ctt.example.pl/wp-admin/x</loc></url>
<url><loc>https://ctt.example.pl/aktualnosci/z-mapy</loc></url>
</urlset>"""

SITEMAP_INDEX = """<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://ctt.example.pl/sitemap-posts.xml</loc></sitemap></sitemapindex>"""

CHALLENGE = "<html><body>Request unsuccessful. Incapsula incident ID: 123</body></html>"


def make_site(**kw) -> Site:
    base = dict(id="ctt_test", name="Centrum Transferu Technologii PRz", category="nauka",
                start=["https://ctt.example.pl/aktualnosci"], owner={"name": "Politechnika Rzeszowska",
                "type": "university", "voivodeship": "podkarpackie"},
                include=[r"^/aktualnosci"], use_sitemap=False, delay=0)
    base.update(kw)
    return Site(**base)


class _Resp:
    def __init__(self, url, status, body, headers):
        self.url, self.status, self._body = url, status, body
        self.headers = Message()
        for k, v in headers.items():
            self.headers[k] = v

    def read(self, n=-1):
        return self._body if n < 0 else self._body[:n]

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeWeb:
    """url -> (status, body, headers). Records every request; honours If-None-Match with 304."""

    def __init__(self, pages: dict):
        self.pages = dict(pages)
        self.requests: list[tuple[str, dict]] = []

    def __call__(self, req, timeout):
        url = req.full_url
        headers = {k.lower(): v for k, v in req.header_items()}
        self.requests.append((url, headers))
        if url not in self.pages:
            raise urllib.error.HTTPError(url, 404, "Not Found", Message(), io.BytesIO(b""))
        status, body, hdrs = self.pages[url]
        if isinstance(body, str):
            body = body.encode("utf-8")
        etag = hdrs.get("ETag")
        if etag and headers.get("if-none-match") == etag:
            raise urllib.error.HTTPError(url, 304, "Not Modified", Message(), io.BytesIO(b""))
        if status >= 400:
            raise urllib.error.HTTPError(url, status, "err", Message(), io.BytesIO(body))
        return _Resp(url, status, body, hdrs)

    def urls(self):
        return [u for u, _ in self.requests]


def html(body: str, etag: str | None = None):
    h = {"Content-Type": "text/html; charset=utf-8"}
    if etag:
        h["ETag"] = etag
    return (200, body, h)
