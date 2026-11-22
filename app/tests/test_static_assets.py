"""Issue #31, etap 4: lekka statyka. Obrazy WebP <= 150 KB, każdy <img> z width/height, cache i kompresja odpowiedzi,
pełny poland.json nie jest pobierany przy starcie. Bez sieci: TestClient i pliki z repo."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

STATIC = Path(__file__).resolve().parents[1] / "radar" / "api" / "static"
SOURCES = ("index.html", "app.js", "pages.js", "guides.js")
# Obrazy tworzone w JS bez znacznika <img> (nie mają atrybutów width/height w źródle, rozmiar daje CSS/kanwa):
DYNAMIC_IMAGES = {"app.js": 1}  # `new Image()` w drawGraph(): ikony hubów rysowane na kanwie grafu


def _client():
    from radar.api.main import app

    return TestClient(app)


def test_every_webp_is_at_most_150_kb():
    files = sorted(STATIC.rglob("*.webp"))
    assert files, "brak obrazów WebP w static/"
    too_big = {str(p.relative_to(STATIC)): p.stat().st_size // 1024 for p in files if p.stat().st_size > 150 * 1024}
    assert too_big == {}


def test_every_img_tag_has_width_and_height():
    missing = []
    for name in SOURCES:
        src = (STATIC / name).read_text(encoding="utf-8")
        for tag in re.findall(r"<img\b[^>]*>", src):
            if not (re.search(r"\swidth=", tag) and re.search(r"\sheight=", tag)):
                missing.append(f"{name}: {tag[:90]}")
        assert len(re.findall(r"new Image\(", src)) == DYNAMIC_IMAGES.get(name, 0), f"{name}: nowy obraz tworzony dynamicznie"
    assert missing == []


def test_img_tags_decode_async():
    for name in SOURCES:
        for tag in re.findall(r"<img\b[^>]*>", (STATIC / name).read_text(encoding="utf-8")):
            assert 'decoding="async"' in tag, f"{name}: {tag[:90]}"


def test_app_js_has_etag_no_cache_and_revalidates_with_304():
    with _client() as c:
        r = c.get("/static/app.js")
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-cache"
        etag = r.headers["etag"]
        r2 = c.get("/static/app.js", headers={"If-None-Match": etag})
        assert r2.status_code == 304


def test_code_and_styles_revalidate_but_images_are_cached_for_a_week():
    with _client() as c:
        for p in ("/static/pages.js", "/static/app.css", "/static/v3.css", "/"):
            assert c.get(p).headers["cache-control"] == "no-cache", p
        for p in ("/static/banners/home.webp", "/static/icons.svg", "/static/poland.json"):
            cc = c.get(p).headers["cache-control"]
            assert "max-age=604800" in cc and "public" in cc, p


def test_gzip_when_the_client_accepts_it():
    with _client() as c:
        r = c.get("/static/app.js", headers={"Accept-Encoding": "gzip"})
        assert r.headers.get("content-encoding") == "gzip"
        assert "Accept-Encoding" in r.headers.get("vary", "")
        assert c.get("/static/app.js", headers={"Accept-Encoding": "identity"}).headers.get("content-encoding") is None


def test_poland_json_is_not_preloaded_or_fetched_at_boot():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "poland.json" not in html
    assert 'id="pl-shape"' in html  # the loader draws the border from this inline outline
    outline = re.search(r'<path id="pl-shape" d="([^"]+)"', html).group(1)
    assert len(outline) < 10_000
    pages = (STATIC / "pages.js").read_text(encoding="utf-8")
    assert 'api("/static/poland.json")' not in pages  # only drawPoland() (app.js) fetches it, on demand
    assert (STATIC / "app.js").read_text(encoding="utf-8").count("/static/poland.json") == 1
