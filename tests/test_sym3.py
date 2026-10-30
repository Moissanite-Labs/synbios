import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from synbios.sym3 import reproduce, tokens
from synbios.sym3.canonical import canonical_payload, messages_equal, normalize_message
from synbios.sym3.decoder_context import parse_decoder_context, setup_sizes
from synbios.sym3.encoders import all_encoders, decode_transcript, encode_transcript
from synbios.sym3.fixtures import lifecycle_11, lifecycle_40, lifecycle_200
from synbios.sym3.generate_lexicon import render_lexicon
from synbios.sym3.lexicon import LEXICON_PATH, load_lexicon
from synbios.sym3.tokens import TokenizerUnavailable, is_single_token, load_tokenizers, require_bench_tokenizers


def _bench_tokenizers_or_skip(test):
    try:
        return require_bench_tokenizers()
    except TokenizerUnavailable:
        test.skipTest("pinned bench tokenizers unavailable")


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
    def _assert_round_trip(self, messages, encoder_name):
        enc = all_encoders()[encoder_name]
        lines = encode_transcript(enc, messages)
        back = decode_transcript(enc, lines)
        self.assertEqual(len(back), len(messages))
        for exp, got in zip(messages, back):
            self.assertTrue(messages_equal(exp, got), f"{encoder_name}: {exp} vs {got}")

    def test_all_encoders_round_trip_11(self):
        messages = lifecycle_11()
        for name in all_encoders():
            with self.subTest(encoder=name, transcript="lifecycle_11"):
                self._assert_round_trip(messages, name)

    def test_all_encoders_round_trip_40(self):
        messages = lifecycle_40()
        for name in all_encoders():
            with self.subTest(encoder=name, transcript="lifecycle_40"):
                self._assert_round_trip(messages, name)

    def test_all_encoders_round_trip_200(self):
        messages = lifecycle_200()
        for name in all_encoders():
            with self.subTest(encoder=name, transcript="lifecycle_200"):
                self._assert_round_trip(messages, name)


class Sym3MinimalContextTests(unittest.TestCase):
    LIFECYCLES = (
        ("lifecycle_11", lifecycle_11),
        ("lifecycle_40", lifecycle_40),
        ("lifecycle_200", lifecycle_200),
    )

    def test_minimal_context_decodes_every_encoder(self):
        full_lex = load_lexicon()
        for tname, fn in self.LIFECYCLES:
            messages = fn()
            for enc_name in all_encoders():
                with self.subTest(transcript=tname, encoder=enc_name):
                    enc_full = all_encoders(full_lex)[enc_name]
                    lines = encode_transcript(enc_full, messages)
                    sizes = setup_sizes(messages, lines, full_lex)
                    lex_min, _schema = parse_decoder_context(sizes["minimal_text"])
                    enc_min = all_encoders(lex_min)[enc_name]
                    back = decode_transcript(enc_min, lines)
                    self.assertEqual(len(back), len(messages))
                    for exp, got in zip(messages, back):
                        self.assertTrue(messages_equal(exp, got))


class Sym3BenchSmokeTests(unittest.TestCase):
    def test_minimal_setup_larger_than_header_only(self):
        specs = load_tokenizers()
        if not specs:
            self.skipTest("tiktoken not installed")
        messages = lifecycle_11()
        enc = all_encoders()["combined"]
        lines = encode_transcript(enc, messages)
        sizes = setup_sizes(messages, lines)
        self.assertGreater(sizes["minimal"], sizes["header_only"])
        self.assertGreater(sizes["full"], sizes["minimal"])

    def test_lifecycle_200_length(self):
        self.assertEqual(len(lifecycle_200()), 200)


class Sym3RegenLexiconTests(unittest.TestCase):
    def test_regenerate_lexicon(self):
        specs = _bench_tokenizers_or_skip(self)
        regenerated = render_lexicon(specs)
        json.loads(regenerated)
        # Stable if candidates unchanged; compared in memory, never written.
        self.assertEqual(LEXICON_PATH.read_text(encoding="utf-8"), regenerated)


class Sym3ReproduceVerificationTests(unittest.TestCase):
    """Run reproduce.main against temporary copies so tests never write tracked files."""

    def setUp(self):
        _bench_tokenizers_or_skip(self)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.bench_md = Path(tmp.name) / "sym3-bench.md"
        self.results_json = Path(tmp.name) / "sym3-bench-results.json"
        shutil.copyfile(reproduce.BENCH_MD, self.bench_md)
        for name, path in (("BENCH_MD", self.bench_md), ("RESULTS_JSON", self.results_json)):
            patcher = mock.patch.object(reproduce, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_reproduce_fails_when_committed_bench_corrupted(self):
        original = self.bench_md.read_text(encoding="utf-8")
        corrupted = original.replace("| 682 |", "| 999 |", 1)
        self.assertNotEqual(corrupted, original)
        self.bench_md.write_text(corrupted, encoding="utf-8")
        with self.assertRaises(SystemExit) as ctx:
            reproduce.main([])
        self.assertIn("benchmark mismatch", str(ctx.exception.code))
        self.assertFalse(self.results_json.exists())

    def test_reproduce_passes_against_committed_bench(self):
        self.assertEqual(reproduce.main([]), 0)
        self.assertTrue(self.results_json.is_file())


class Sym3TokenizerLoadingTests(unittest.TestCase):
    """Fake tokenizer modules; no network or real encodings needed."""

    def setUp(self):
        tokens._load.cache_clear()
        self.addCleanup(tokens._load.cache_clear)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(tokens.EXTRA_TOKENIZERS_ENV, None)
        self.loads = []

    def _fake_modules(self, tiktoken_error=None):
        def get_encoding(name):
            self.loads.append(name)
            if tiktoken_error:
                raise tiktoken_error
            return types.SimpleNamespace(encode=lambda text: list(text.encode()))

        def from_pretrained(model_id):
            return types.SimpleNamespace(encode=lambda text, add_special_tokens: types.SimpleNamespace(ids=[1]))

        tiktoken = types.SimpleNamespace(get_encoding=get_encoding)
        hf = types.SimpleNamespace(Tokenizer=types.SimpleNamespace(from_pretrained=from_pretrained))
        return mock.patch.dict(sys.modules, {"tiktoken": tiktoken, "tokenizers": hf})

    def test_pinned_set_is_default_and_cached(self):
        with self._fake_modules():
            self.assertEqual([s.name for s in load_tokenizers()], list(tokens.BENCH_TOKENIZERS))
            self.assertEqual([s.name for s in require_bench_tokenizers()], list(tokens.BENCH_TOKENIZERS))
            load_tokenizers()
        self.assertEqual(self.loads, list(tokens.BENCH_TOKENIZERS))

    def test_extra_tokenizers_are_opt_in_and_refused_by_bench(self):
        os.environ[tokens.EXTRA_TOKENIZERS_ENV] = "1"
        with self._fake_modules():
            self.assertEqual([s.name for s in load_tokenizers()], [*tokens.BENCH_TOKENIZERS, "qwen2"])
            with self.assertRaisesRegex(TokenizerUnavailable, tokens.EXTRA_TOKENIZERS_ENV):
                require_bench_tokenizers()

    def test_unavailable_tiktoken_reports_cause_not_mismatch(self):
        with self._fake_modules(OSError("encoding download blocked")):
            self.assertEqual(load_tokenizers(), [])
            with self.assertRaises(SystemExit) as ctx:
                reproduce.main([])
        message = str(ctx.exception.code)
        self.assertIn("encoding download blocked", message)
        self.assertIn("TIKTOKEN_CACHE_DIR", message)
        self.assertNotIn("mismatch", message)


if __name__ == "__main__":
    unittest.main()
