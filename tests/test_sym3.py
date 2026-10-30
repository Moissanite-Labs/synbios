import json
import unittest

from synbios.sym3.canonical import canonical_payload, messages_equal, normalize_message
from synbios.sym3.encoders import (
    all_encoders,
    decode_transcript,
    encode_transcript,
    setup_prefix,
)
from synbios.sym3.fixtures import lifecycle_11, lifecycle_40
from synbios.sym3.generate_lexicon import main as regen_lexicon
from synbios.sym3.lexicon import LEXICON_PATH, load_lexicon
from synbios.sym3.tokens import is_single_token, load_tokenizers


class Sym3LexiconTests(unittest.TestCase):
    def test_lexicon_file_exists(self):
        self.assertTrue(LEXICON_PATH.is_file())
        lex = load_lexicon()
        self.assertIn("cmd", lex.raw)
        self.assertIn("project.create", lex.raw["cmd"])

    def test_format_tags_single_token(self):
        specs = load_tokenizers()
        if not specs:
            self.skipTest("tiktoken not installed")
        primary = specs[0]
        lex = load_lexicon()
        for name, tag in lex.format_tags.items():
            self.assertTrue(is_single_token(tag, [primary]), f"tag {name}={tag!r}")


class Sym3RoundTripTests(unittest.TestCase):
    def test_all_encoders_round_trip_11(self):
        messages = lifecycle_11()
        for name, enc in all_encoders().items():
            with self.subTest(encoder=name):
                lines = encode_transcript(enc, messages)
                back = decode_transcript(enc, lines)
                self.assertEqual(len(back), len(messages))
                for exp, got in zip(messages, back):
                    self.assertTrue(messages_equal(exp, got), f"{name}: {exp} vs {got}")

    def test_combined_round_trip_40(self):
        messages = lifecycle_40()
        enc = all_encoders()["combined"]
        lines = encode_transcript(enc, messages)
        back = decode_transcript(enc, lines)
        for exp, got in zip(messages, back):
            self.assertTrue(messages_equal(exp, got))


class Sym3BenchSmokeTests(unittest.TestCase):
    def test_setup_prefix_tokenizable(self):
        specs = load_tokenizers()
        if not specs:
            self.skipTest("tiktoken not installed")
        text = setup_prefix()
        self.assertGreater(len(text), 0)


class Sym3RegenLexiconTests(unittest.TestCase):
    def test_regenerate_lexicon(self):
        specs = load_tokenizers()
        if not specs:
            self.skipTest("tiktoken not installed")
        before = LEXICON_PATH.read_text(encoding="utf-8")
        self.assertEqual(regen_lexicon(), 0)
        after = LEXICON_PATH.read_text(encoding="utf-8")
        json.loads(after)
        # Stable if candidates unchanged
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
