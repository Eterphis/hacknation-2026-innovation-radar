import io
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from radar.http import BinaryResponse, Response
from radar.sources import interreg
from radar.xlsx import excel_date, read_rows

TODAY = date(2026, 11, 21)
HEADER = ["Program / Programme", "Numer projektu / Project no.", "Tytul projektu / Project title",
          "Opis projektu / Project description", "Data rozpoczęcia realizacji / Project start date",
          "Data zakończenia realizacji / Project end date", "Wydatki 0gółem (EUR) / Total costs (EUR)",
          "Stopa dofinansowania unijnego / EU co-financing rate", "Fundusz / Fund", "Cel szczegółowy / Specific objective",
          "Nazwa partnera wiodącego/ Lead partner name", "Kod pocztowy / Postal code", "Kraj / Country",
          "Województwo lub region / Voivodeship or region ", "Powiat / Poviat", "Gmina / Commune", "Miejscowość / City",
          "Nazwa partnera wiodącego i partnerów / Lead partner and partners name", "Zakres interwencji / Intevention field",
          "Projekt strategiczny/ Project of strategic importance", "Projekt powyżej 5 mln EUR / Project above 5 mln EUR"]
DESC = "Projekt rozwija wspólny system ostrzegania przed powodzią dla gmin po obu stronach granicy. " * 4
ROWS = [
    ["Lista projektów programów Interreg 2021-2027"],
    HEADER,
    ["Program Interreg Polska-Słowacja 2021-2027", "PLSK.01.01-IP.01-0002/23", "Od Beskidu Niskiego po Solinę/Od Nizkych Beskid",
     DESC, 45292.041666666664, 46022.041666666664, 1307775.51, 80, "EFRR", "CP2.IV Klimat", "Województwo Podkarpackie",
     "35-010", "Polska", "PODKARPACKIE", "Rzeszów", "Rzeszów", "Rzeszów",
     "Województwo Podkarpackie | Správa a údržba ciest Prešovského samosprávneho kraja", "058 Klimat", "N", "N"],
    ["Interreg South Baltic", "STHB.01.01-IP.01-0001/24", "Krótki", "za krótki opis", 46400, 47000, "abc", 90, "EFRR", "",
     "Kommune Bornholm", "", "Dania", "Hovedstaden", "", "", "Rønne", "Kommune Bornholm | Gmina Ustka", "", "T", "N"],
]


def make_xlsx(rows) -> bytes:
    def col(i):
        s = ""
        i += 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s
    strings: list[str] = []
    sheet_rows = []
    for ri, row in enumerate(rows, 1):
        cells = []
        for ci, v in enumerate(row):
            ref = f"{col(ci)}{ri}"
            if isinstance(v, (int, float)):
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                strings.append(v)
                cells.append(f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>')
        sheet_rows.append(f'<row r="{ri}">{"".join(cells)}</row>')
    m = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {m} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                                      '<sheets><sheet name="Arkusz1" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                                 '<Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="x"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f'<sst {m}>' + "".join(f"<si><t>{escape(s)}</t></si>" for s in strings) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {m}><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>')
    return buf.getvalue()


class XlsxTest(unittest.TestCase):
    def test_read_rows_and_dates(self):
        rows = read_rows(make_xlsx(ROWS))
        self.assertEqual(rows[1][6], HEADER[6])
        self.assertEqual(rows[2][1], "PLSK.01.01-IP.01-0002/23")
        self.assertEqual(excel_date(rows[2][4]), date(2024, 1, 1))
        self.assertIsNone(excel_date("abc"))


class InterregTest(unittest.TestCase):
    def setUp(self):
        self.mapping, self.data = interreg.parse_sheet(read_rows(make_xlsx(ROWS)))

    def test_header_found_despite_typo(self):
        self.assertEqual(self.mapping["total"], 6)  # "Wydatki 0gółem"
        self.assertEqual(self.mapping["lead"], 10)
        self.assertEqual(self.mapping["partners"], 17)
        self.assertEqual(len(self.data), 2)
        self.assertEqual(self.data[0][0], 3)  # excel row number

    def test_record(self):
        excel_row, values = self.data[0]
        r = interreg.build_record(values, excel_row=excel_row, file_url="https://x/w.xlsx", list_fetched_at="L",
                                  file_fetched_at="F", today=TODAY)
        self.assertEqual(r["record_id"], "plsk-01-01-ip-01-0002-23")
        self.assertEqual(r["funding"]["total_value"], 1307775.51)
        self.assertEqual(r["funding"]["grant_value"], 1046220.41)
        self.assertEqual(r["funding"]["grant_share"], 0.8)
        self.assertEqual((r["period"]["start"], r["period"]["end"], r["period"]["status"]), ("2024-01-01", "2025-12-31", "finished"))
        self.assertEqual(r["region"]["voivodeships"], ["podkarpackie"])
        roles = [(o["name"], o["role"], o["type_hint"]) for o in r["organizations"]]
        self.assertEqual(roles, [("Województwo Podkarpackie", "lead_partner", "local_government"),
                                 ("Správa a údržba ciest Prešovského samosprávneho kraja", "partner", None)])
        self.assertEqual(r["organizations"][0]["location"]["postal_code"], "35-010")
        self.assertEqual(r["quality"]["status"], "ok")
        self.assertEqual(r["provenance"]["source_row"], 3)

    def test_foreign_and_bad_values(self):
        excel_row, values = self.data[1]
        r = interreg.build_record(values, excel_row=excel_row, file_url=None, list_fetched_at=None,
                                  file_fetched_at=None, today=TODAY)
        self.assertEqual(r["region"], {"voivodeships": [], "nationwide": False, "raw": "Hovedstaden", "country": "Dania"})
        self.assertIn("short_text", r["quality"]["blocking"])
        self.assertIn("total_value_unparsed", r["quality"]["warnings"])
        self.assertEqual(r["period"]["status"], "planned")
        self.assertTrue(r["funding"]["strategic_project"])

    def test_missing_required_columns(self):
        with self.assertRaises(interreg.FormatChanged):
            interreg.parse_sheet([["coś"], ["inna", "tabela"]])

    def test_link_from_page(self):
        html = '<a href="/x.pdf">a</a><a href="/wp-content/uploads/2026/11/Wykaz_projektow_Interreg_20261116.xlsx">XLSX</a>'
        self.assertEqual(interreg.find_xlsx_link(html),
                         "https://interreg.gov.pl/wp-content/uploads/2026/11/Wykaz_projektow_Interreg_20261116.xlsx")

    def test_harvest_online_then_offline(self):
        xlsx = make_xlsx(ROWS)
        page = '<a href="/wp-content/uploads/Wykaz_projektow.xlsx">XLSX</a>'
        with tempfile.TemporaryDirectory() as tmp:
            store = interreg.RawStore(Path(tmp))
            got = list(interreg.harvest(
                store,
                page_fetcher=lambda u: Response(u, 200, page, "2026-11-21T10:00:00+00:00"),
                file_fetcher=lambda u: BinaryResponse(u, 200, xlsx, "application/xlsx", "2026-11-21T10:00:01+00:00"),
                today=TODAY))
            self.assertEqual(len(got), 2)
            self.assertTrue(Path(got[0]["provenance"]["raw_files"]["source_file"]).exists())
            offline = list(interreg.harvest(store, offline=True, today=TODAY))
            self.assertEqual([r["content_hash"] for r in offline], [r["content_hash"] for r in got])


if __name__ == "__main__":
    unittest.main()
