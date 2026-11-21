import copy
import json
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from radar import assess
from radar.card import build_card, render_justification
from radar.extract import LLMError, run_extraction, source_text, validate
from radar.llm import ClaudeExtractor, RulesExtractor
from radar.sources import ncbr

FIX = Path(__file__).parent / "fixtures" / "ncbr"


def czujnik_record() -> dict:
    card = ncbr.parse_list((FIX / "list_sample.html").read_text("utf-8"))[0]
    detail = ncbr.parse_detail((FIX / "detail_czujnik.html").read_text("utf-8"))
    return ncbr.build_record(card, detail, list_fetched_at="L", detail_fetched_at="D", today=date(2026, 11, 21))


def good_extraction(record: dict) -> dict:
    return RulesExtractor().extract(source_text(record), record)


class FakeProvider:
    def __init__(self, name, answers):
        self.name, self.model, self.answers, self.calls = name, None, list(answers), []

    def extract(self, source_text, record, feedback=None):
        self.calls.append(feedback)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return copy.deepcopy(answer)


class ValidateTest(unittest.TestCase):
    def setUp(self):
        self.rec = czujnik_record()
        self.src = source_text(self.rec)

    def test_rules_output_is_valid(self):
        self.assertEqual(validate(good_extraction(self.rec), self.src), [])

    def test_paraphrased_quote_is_rejected(self):
        data = good_extraction(self.rec)
        data["problem_solved"]["quote"] = "Czujniki są potrzebne, bo automatyzacja szybko rośnie."
        self.assertTrue(any(e.startswith("problem_solved") for e in validate(data, self.src)))

    def test_quote_tolerates_spacing_and_quotes(self):
        data = good_extraction(self.rec)
        data["what_is_new"]["quote"] = "  innowacyjny   czujnik światłowodowy do monitorowania odkształceń "
        data["what_is_new"]["value"] = "czujnik światłowodowy"
        self.assertEqual(validate(data, self.src), [])

    def test_short_names_only_as_whole_words(self):
        from radar.extract import _norm, quote_in_source
        src = _norm("Tytuł: Cypherdog\n\nSystem dla firm.")
        self.assertTrue(quote_in_source("Cypherdog", src))
        self.assertFalse(quote_in_source("dla", src[:0] + "systemdla"))
        self.assertFalse(quote_in_source("pher", src))

    def test_unknown_enum_rejected(self):
        data = good_extraction(self.rec)
        data["target_users"].append({"who": "ktoś", "recipient_type": "kosmici", "quote": data["problem_solved"]["quote"]})
        self.assertTrue(any("typ spoza listy" in e for e in validate(data, self.src)))


class RunExtractionTest(unittest.TestCase):
    def setUp(self):
        self.rec = czujnik_record()
        self.good = good_extraction(self.rec)

    def test_retry_with_feedback_then_success(self):
        bad = copy.deepcopy(self.good)
        bad["what_is_new"] = {"value": "coś nowego", "quote": "tego zdania nie ma w tekście źródłowym"}
        p = FakeProvider("fake", [bad, self.good])
        res = run_extraction(self.rec, [p])
        self.assertEqual(res.attempts, 2)
        self.assertIsNone(p.calls[0])
        self.assertTrue(any("what_is_new" in e for e in p.calls[1]))

    def test_unverifiable_claims_dropped_after_retries(self):
        bad = copy.deepcopy(self.good)
        bad["what_is_new"] = {"value": "coś nowego", "quote": "tego zdania nie ma w tekście źródłowym"}
        res = run_extraction(self.rec, [FakeProvider("fake", [bad, bad, bad])])
        self.assertEqual(res.data["what_is_new"], {"value": "", "quote": ""})
        self.assertIn("what_is_new", res.dropped)

    def test_fallback_to_next_provider_on_error(self):
        res = run_extraction(self.rec, [FakeProvider("broken", [LLMError("timeout")]), RulesExtractor()])
        self.assertEqual(res.provider, "offline_rules")
        self.assertIn("broken: timeout", res.fallback_reason)


class ClaudeExtractorTest(unittest.TestCase):
    """The Claude adapter against a stand-in client: request shape and stop-reason handling."""

    def make(self, stop_reason="end_turn", payload=None):
        sent = {}

        def create(**kwargs):
            sent.update(kwargs)
            content = [SimpleNamespace(type="thinking", thinking=""),
                       SimpleNamespace(type="text", text=json.dumps(payload or {}))]
            return SimpleNamespace(stop_reason=stop_reason, content=content, model=kwargs["model"])

        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        return ClaudeExtractor(client=client), sent

    def test_request_uses_schema_and_fallbacks(self):
        rec = czujnik_record()
        good = good_extraction(rec)
        ext, sent = self.make(payload=good)
        out = ext.extract(source_text(rec), rec, feedback=["what_is_new: cytat nie występuje"])
        self.assertEqual(out, good)
        self.assertEqual(sent["model"], "claude-opus-5-5")
        self.assertEqual(sent["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(sent["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", sent["betas"])
        self.assertNotIn("thinking", sent)
        self.assertIn("what_is_new: cytat", sent["messages"][0]["content"])

    def test_refusal_becomes_llm_error_and_rules_take_over(self):
        rec = czujnik_record()
        ext, _ = self.make(stop_reason="refusal")
        with self.assertRaises(LLMError):
            ext.extract(source_text(rec), rec)
        res = run_extraction(rec, [ext, RulesExtractor()])
        self.assertEqual(res.provider, "offline_rules")


class AssessTest(unittest.TestCase):
    def test_maturity_levels(self):
        ex = {"maturity_signals": [{"signal": "demonstrator", "quote": "q"}]}
        m = assess.maturity(ex)
        self.assertEqual((m["level"], m["hidden"]), ("tech_ready", True))
        ex["maturity_signals"].append({"signal": "produkt_na_rynku", "quote": "q"})
        m = assess.maturity(ex)
        self.assertEqual((m["level"], m["hidden"]), ("market_ready", False))
        self.assertEqual(assess.maturity({"maturity_signals": []})["level"], "exploring")

    def test_cost_regex_does_not_match_inside_words(self):
        import re
        self.assertIsNone(re.search(assess.COST_HINT_RE, "szerokie wykorzystanie uzdatnionej wody"))
        self.assertIsNotNone(re.search(assess.COST_HINT_RE, "jest prosty w implementacji"))

    def test_missing_cost_is_a_gap_not_a_guess(self):
        rec = czujnik_record()
        rec["text"] = {"problem": "Problem opisany bez kosztów."}
        ex = good_extraction(czujnik_record())
        ex["requirements"] = {"value": "", "quote": ""}
        sc = assess.score(rec, ex, assess.maturity(ex))
        cost = next(c for c in sc["criteria"] if c["key"] == "koszt_wdrozenia")
        self.assertIsNone(cost["score"])
        self.assertEqual(sc["scored_criteria"], 4)

    def test_route_for_education(self):
        rec = czujnik_record()
        ex = good_extraction(rec)
        ex["innovation_type"] = "edukacyjna"
        mat = assess.maturity(ex)
        self.assertEqual(assess.route(rec, ex, mat, assess.score(rec, ex, mat))["path"], "replikacja")


class CardTest(unittest.TestCase):
    def test_card_end_to_end_offline(self):
        rec = czujnik_record()
        card = build_card(rec, [RulesExtractor()], now="2026-11-21T00:00:00+00:00")
        self.assertEqual(card["status"], "ready")
        self.assertEqual(card["maturity"]["level"], "tech_ready")
        self.assertTrue(card["maturity"]["hidden"])
        self.assertIn("lotnictwo", card["route"]["pci_priority_sectors"])
        self.assertTrue(any(r["recipient_type"] == "ochrona_zdrowia" for r in card["route"]["recipients"]))
        self.assertEqual(card, build_card(rec, [RulesExtractor()], now="2026-11-21T00:00:00+00:00"))  # deterministic
        md = render_justification(card)
        for heading in ("## 1. Co ustalono", "## 2.", "## 3. Ocena", "## 4. Co przemawia przeciw",
                        "## 5. Rozstrzygnięcie", "## 6. Ograniczenia"):
            self.assertIn(heading, md)
        self.assertIn("Demonstrator", md)
        json.dumps(card)

    def test_card_when_all_providers_fail(self):
        card = build_card(czujnik_record(), [FakeProvider("x", [LLMError("down")])])
        self.assertEqual(card["status"], "needs_review")
        self.assertIn("Karta niekompletna", render_justification(card))


if __name__ == "__main__":
    unittest.main()
