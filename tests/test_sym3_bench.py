import copy
import json
import unittest
from pathlib import Path

from synbios.sym3.bench import KEY_VALUE_LABEL, format_markdown

DOCS = Path(__file__).resolve().parents[1] / "docs"


def _normalize(text):
    return text.replace("\r\n", "\n").strip() + "\n"


class Sym3BenchMarkdownTests(unittest.TestCase):
    """Network-free: render the committed results and compare with the committed tables."""

    def setUp(self):
        self.results = json.loads((DOCS / "sym3-bench-results.json").read_text(encoding="utf-8"))
        self.primary = self.results["primary_tokenizer"]

    def lifecycle_11(self, transcripts):
        rows = next(b for b in transcripts if b["transcript"] == "lifecycle_11")["rows"]
        return {r["label"]: r for r in rows}

    def verdict(self, transcripts):
        return format_markdown(transcripts, self.primary).split("## Verdict", 1)[1]

    def test_committed_tables_match_committed_results(self):
        self.assertEqual(
            _normalize(format_markdown(self.results["transcripts"], self.primary)),
            _normalize((DOCS / "sym3-bench.md").read_text(encoding="utf-8")),
        )

    def test_verdict_follows_the_numbers(self):
        transcripts = copy.deepcopy(self.results["transcripts"])
        rows = self.lifecycle_11(transcripts)
        rows["SYM-3 refs"]["total_primary"][self.primary] = 700
        rows["SYM-3 adaptive"]["total_full"][self.primary] = 640
        rows[KEY_VALUE_LABEL]["total_primary"][self.primary] = 777
        verdict = self.verdict(transcripts)
        self.assertIn("SYM-3 **refs** totals **700** vs compact JSON **682**", verdict)
        self.assertIn("(does not win)", verdict)
        self.assertIn("**Adaptive** is **512** (below JSON)", verdict)
        # Full totals on opposite sides of JSON (682) get their own comparisons.
        self.assertIn(
            "refs **765** (524 + messages, **above** compact JSON) and "
            "adaptive **640** (524 + messages, **below** compact JSON) at 11 messages",
            verdict,
        )
        self.assertIn("key=value text **777**", verdict)
        self.assertNotIn("491", verdict)

    def test_full_setup_is_attributed_per_encoder(self):
        transcripts = copy.deepcopy(self.results["transcripts"])
        rows = self.lifecycle_11(transcripts)
        rows["SYM-3 adaptive"]["setup_full"][self.primary] = 400
        rows["SYM-3 adaptive"]["total_full"][self.primary] = 641
        self.assertIn("adaptive **641** (400 + messages, **below** compact JSON)", self.verdict(transcripts))

    def test_shared_full_phrase_when_encoders_agree(self):
        transcripts = copy.deepcopy(self.results["transcripts"])
        rows = self.lifecycle_11(transcripts)
        for label in ("SYM-3 refs", "SYM-3 adaptive"):
            rows[label]["total_full"][self.primary] = 600
        self.assertIn(
            "Under **full** setup (524 + messages), refs/adaptive **600** — **below** compact JSON at 11 messages.",
            self.verdict(transcripts),
        )

    def test_key_value_baseline_is_not_called_english(self):
        rows = self.lifecycle_11(self.results["transcripts"])
        self.assertIn(KEY_VALUE_LABEL, rows)
        self.assertFalse(any("terse" in label or "CoD" in label for label in rows))


if __name__ == "__main__":
    unittest.main()
