import unittest
from datetime import date

from radar.pl import parse_money, parse_period, parse_voivodeships

TODAY = date(2026, 11, 21)


class MoneyTest(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_money("1 186 431,74 zł"), (1186431.74, "PLN"))
        self.assertEqual(parse_money("169000,00 PLN"), (169000.0, "PLN"))
        self.assertEqual(parse_money("2.945.328,25 zł"), (2945328.25, "PLN"))
        self.assertEqual(parse_money("1.500.000 zł"), (1500000.0, "PLN"))
        self.assertEqual(parse_money("1 000 000 zł"), (1000000.0, "PLN"))

    def test_missing(self):
        self.assertEqual(parse_money(None), (None, None))
        self.assertEqual(parse_money("brak danych")[0], None)


class PeriodTest(unittest.TestCase):
    def check(self, raw, start, end, precision, status):
        p = parse_period(raw, today=TODAY)
        self.assertEqual((p.start, p.end, p.precision, p.status), (start, end, precision, status), raw)

    def test_seen_on_ncbr(self):
        self.check("od 01.02.2016 r. do 31.01.2019 r.", "2016-02-01", "2019-01-31", "day", "finished")
        self.check("od 11-02-2019 r. do 30-09-2021 r.", "2019-02-11", "2021-09-30", "day", "finished")
        self.check("od 1 grudnia 2018r. do 31 października 2021r.", "2018-12-01", "2021-10-31", "day", "finished")
        self.check("01.10.2019 - 31.03.2022", "2019-10-01", "2022-03-31", "day", "finished")
        self.check("1 lipca 2015 r. – 31 maja 2019 r.", "2015-07-01", "2019-05-31", "day", "finished")

    def test_sloppy_spacing_from_ncbr(self):
        self.check("od 01-11- 2017r. do 31-10-2018 r.", "2017-11-01", "2018-10-31", "day", "finished")
        self.check("od 1 listopada2017 r. do 31 października2018 r.", "2017-11-01", "2018-10-31", "day", "finished")
        self.check("od 01.02.2021r. do 30.11.2022 r.", "2021-02-01", "2022-11-30", "day", "finished")
        self.check("od 1.09.2017r. do 31.08.2022r. (przedłużony do 31.10.2023)",
                   "2017-09-01", "2022-08-31", "day", "finished")

    def test_month_and_year(self):
        self.check("od marca 2025 do czerwca 2027", "2025-03-01", "2027-06-30", "month", "running")
        self.check("2019-2021", "2019-01-01", "2021-12-31", "year", "finished")

    def test_ongoing(self):
        p = parse_period("Od 2018 r. – projekt w toku", today=TODAY)
        self.assertEqual((p.start, p.end, p.status, p.ongoing), ("2018-01-01", None, "running", True))

    def test_planned_and_unparsed(self):
        self.check("od 01.01.2027 do 31.12.2028", "2027-01-01", "2028-12-31", "day", "planned")
        self.check("brak", None, None, None, None)


class VoivodeshipTest(unittest.TestCase):
    def test_names(self):
        self.assertEqual(parse_voivodeships("województwo lubelskie"), (["lubelskie"], False))
        self.assertEqual(parse_voivodeships("Mazowieckie"), (["mazowieckie"], False))
        self.assertEqual(parse_voivodeships("Śląskie, Małopolskie"), (["śląskie", "małopolskie"], False))

    def test_compound_not_double_counted(self):
        self.assertEqual(parse_voivodeships("kujawsko-pomorskie"), (["kujawsko-pomorskie"], False))
        self.assertEqual(parse_voivodeships("warmińsko-mazurskie i pomorskie"),
                         (["warmińsko-mazurskie", "pomorskie"], False))

    def test_typos_from_ncbr(self):
        self.assertEqual(parse_voivodeships("zachodnioporskie"), (["zachodniopomorskie"], False))
        self.assertEqual(parse_voivodeships("warmińsko mazurskie"), (["warmińsko-mazurskie"], False))
        self.assertEqual(parse_voivodeships("Kraków i okolice"), ([], False))

    def test_nationwide(self):
        self.assertEqual(parse_voivodeships("cała Polska"), ([], True))
        self.assertEqual(parse_voivodeships(""), ([], False))


if __name__ == "__main__":
    unittest.main()
