"""Issue #30 task 6: calls for proposals from schedule tables (DOCX built in the test, CSV fixture), matching."""

import io
import os
import zipfile
from datetime import date
from pathlib import Path

import httpx

from radar.sources import calls as C
from radar.sources.disk_cache import DiskCache

FIX = Path(__file__).parent / "fixtures" / "issue30"
CSV_NAME = "harmonogram_fe_dla_podkarpacia.csv"
TODAY = date(2026, 11, 22)


def _docx(rows: list[list[str]]) -> bytes:
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    cell = lambda t: f"<w:tc><w:p><w:r><w:t>{t}</w:t></w:r></w:p></w:tc>"  # noqa: E731
    body = "".join("<w:tr>" + "".join(cell(c) for c in r) + "</w:tr>" for r in rows)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document {ns}><w:body><w:p/><w:tbl>{body}</w:tbl></w:body></w:document>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


NATIONAL = _docx([
    ["Harmonogram naborów wniosków FENG 2021-2027"],
    ["Program", "Działanie", "Nazwa naboru", "Typ wnioskodawców", "Planowany termin rozpoczęcia naboru",
     "Planowany termin zakończenia naboru", "Kwota"],
    ["Fundusze Europejskie dla Nowoczesnej Gospodarki", "FENG.01.01", "Ścieżka SMART: prace B+R i wdrożenie innowacji",
     "przedsiębiorstwa, konsorcja z jednostkami naukowymi", "01.12.2026", "31.03.2027", "1,5 mld zł"],
    ["Fundusze Europejskie dla Nowoczesnej Gospodarki", "FENG.02.07", "Inkubator innowacyjności dla uczelni",
     "uczelnie, instytuty badawcze", "III kwartał 2025", "IV kwartał 2025", "100 mln zł"],
])


def _calls():
    csv_calls = C.calls_from_bytes((FIX / CSV_NAME).read_bytes(), CSV_NAME, "plik " + CSV_NAME, "2026-11-22T00:00:00+00:00")
    nat = C.calls_from_bytes(NATIONAL, "feng.docx", "https://example.invalid/feng.docx", "2026-11-22T00:00:00+00:00")
    return csv_calls, nat


def test_dates_and_amounts():
    assert C.parse_when("15.03.2026") == ("2026-03-15", "day")
    assert C.parse_when("III kwartał 2026") == ("2026-07-01", "quarter")
    assert C.parse_when("III kwartał 2026", end=True) == ("2026-09-30", "quarter")
    assert C.parse_when("luty 2028", end=True) == ("2028-02-29", "month")
    assert C.parse_when("do ustalenia") == (None, None)
    assert C._amount("1,5 mld zł") == 1.5e9 and C._amount("25 000 000,00") == 25e6
    assert C._amount("1.5 mln zł") == 1.5e6 and C._amount("12.500.000,00 zł") == 12.5e6 and C._amount("1.500 tys.") == 1.5e6
    assert C.parse_when("13.2026", end=True) == ("2026-12-31", "year")  # no month 13: not silently January
    assert C.parse_when("03.2026", end=True) == ("2026-03-31", "month")


def test_programme_regions():
    assert C.voivodeships_of("Fundusze Europejskie dla Podkarpacia 2021-2027") == ["podkarpackie"]
    assert C.voivodeships_of("FE dla Pomorza Zachodniego") == ["zachodniopomorskie"]
    assert C.voivodeships_of("Fundusze Europejskie dla Pomorza") == ["pomorskie"]
    assert C.voivodeships_of("Fundusze Europejskie dla Polski Wschodniej") == C.EASTERN
    assert C.voivodeships_of("Fundusze Europejskie dla Nowoczesnej Gospodarki") is None


def test_tables_become_calls_with_source_and_date():
    csv_calls, nat = _calls()
    assert len(csv_calls) == 3 and len(nat) == 2
    pv = next(c for c in csv_calls if "Fotowoltaika" in c["title"])
    assert pv["voivodeships"] == ["podkarpackie"] and "jst" in pv["applicant_types"] and "D_energetyka" in pv["sectors"]
    assert pv["start"] == "2026-10-15" and pv["end"] == "2027-01-15" and pv["amount_pln"] == 25e6
    smart = next(c for c in nat if "SMART" in c["title"])
    assert smart["voivodeships"] is None and "firma" in smart["applicant_types"] and smart["amount_pln"] == 1.5e9
    assert all(c["source"] and c["fetched_at"] and c["id"] for c in csv_calls + nat)


def test_upcoming_filters_closed_region_and_relevance():
    csv_calls, nat = _calls()
    allc = csv_calls + nat
    got = C.upcoming(allc, sector="D_energetyka", institution_type="jst", voivodeship="podkarpackie", today=TODAY)
    assert got[0]["title"].startswith("Fotowoltaika") and got[0]["status"] == "trwa" and "sektor" in got[0]["why"]
    titles = [c["title"] for c in C.upcoming(allc, sector="P_edukacja", institution_type="szkola", voivodeship="podkarpackie", today=TODAY)]
    assert not any("Kompetencje" in t for t in titles)  # closed in May 2026
    firm = C.upcoming(allc, sector="C_przemysl", institution_type="firma", voivodeship="mazowieckie", today=TODAY)
    assert [c["title"] for c in firm] == ["Ścieżka SMART: prace B+R i wdrożenie innowacji"]  # Podkarpacie calls excluded
    assert C.upcoming(allc, sector="uczelnia", institution_type="uczelnia", voivodeship="mazowieckie", today=TODAY) == []


def test_source_is_optional_and_failures_are_skipped(tmp_path):
    assert C.CallsSource([], None).load() == []
    (tmp_path / "nabory").mkdir()
    (tmp_path / "nabory" / CSV_NAME).write_bytes((FIX / CSV_NAME).read_bytes())
    (tmp_path / "nabory" / "zepsuty.docx").write_bytes(b"not a zip")

    def handler(req):
        return httpx.Response(200, content=NATIONAL) if "ok" in str(req.url) else httpx.Response(503)

    src = C.CallsSource(["https://x.invalid/ok/feng.docx", "https://x.invalid/down.docx"], tmp_path / "nabory",
                        cache=DiskCache("calls", root=tmp_path / "cache"), http=httpx.Client(transport=httpx.MockTransport(handler)))
    got = src.load()
    assert len(got) == 5 and len({c["id"] for c in got}) == 5


def test_undefined_cp1250_bytes_do_not_crash():
    text = "Nazwa naboru;Planowany termin rozpoczęcia naboru\nNabór X;01.12.2026\n"
    got = C.calls_from_bytes(text.encode("cp1250") + b"\x81\x98;x\n", "h.csv", "s")
    assert got[0]["title"] == "Nabór X"


def test_broken_or_oversized_files_are_skipped_not_fatal(tmp_path, monkeypatch):
    d = tmp_path / "nabory"
    d.mkdir()
    (d / CSV_NAME).write_bytes((FIX / CSV_NAME).read_bytes())
    (d / "huge_field.csv").write_bytes(b'a;b\n"' + b"x" * 200_000 + b'";1\n')  # csv.Error: field limit
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", b"<a>" + b" " * (2 * 1024 * 1024) + b"</a>")
    (d / "bomb.docx").write_bytes(bomb.getvalue())
    monkeypatch.setattr(C, "MAX_XML_BYTES", 1024 * 1024)
    padded = io.BytesIO(NATIONAL)
    with zipfile.ZipFile(padded, "a", zipfile.ZIP_STORED) as z:
        z.writestr("pad.bin", os.urandom(300_000))  # a valid DOCX of about 300 kB
    big = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=padded.getvalue())))
    src = C.CallsSource(["https://x.invalid/feng.docx"], d, cache=DiskCache("calls", root=tmp_path / "cache"), http=big)
    assert len(src.load()) == 5  # the three bad local files are skipped; the good CSV (3) and the DOCX (2) load
    monkeypatch.setattr(C, "MAX_FILE_BYTES", 100_000)
    src = C.CallsSource(["https://x.invalid/feng.docx"], d, cache=DiskCache("calls", root=tmp_path / "cache2"), http=big)
    got = src.load()  # the 300 kB response is cut off mid-stream; the 200 kB local file is skipped by size
    assert len(got) == 3 and all(c["voivodeships"] == ["podkarpackie"] for c in got)
