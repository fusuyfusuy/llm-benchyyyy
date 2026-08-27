#!/usr/bin/env python3
"""Unit tests for stealth_model_detector.py (scheck)."""
import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import stealth_model_detector as smd


class TestStealthModelDetector(unittest.TestCase):
    def test_is_stealth_model(self):
        self.assertTrue(smd.is_stealth_model({"id": "stealth/ox-alpha"}))
        self.assertTrue(smd.is_stealth_model({"id": "stealth/"}))  # degenerate but prefix matches
        self.assertFalse(smd.is_stealth_model({"id": "openai/gpt-5"}))
        self.assertFalse(smd.is_stealth_model({"id": "xstealth/foo"}))  # must be prefix, not substring
        self.assertFalse(smd.is_stealth_model({"id": ""}))
        self.assertFalse(smd.is_stealth_model({}))
        self.assertEqual(smd.base_id("stealth/ox-alpha:free"), "stealth/ox-alpha")

    def test_filter_synthetic_catalog(self):
        catalog = {
            "data": [
                {"id": "openai/gpt-5", "name": "GPT-5", "pricing": {"prompt": "1.0", "completion": "2.0"}},
                {"id": "stealth/ox-alpha", "name": "Ox Alpha", "created": 1787256295,
                 "context_length": 1048576, "pricing": {"prompt": "0", "completion": "0"},
                 "architecture": {"modality": "text->text"}},
                {"id": "meta-llama/llama-4", "name": "Llama 4", "pricing": {"prompt": "0", "completion": "0"}},
            ]
        }
        or_map = {m.get("id"): m for m in catalog["data"] if m.get("id")}
        stealth = [r for r in or_map.values() if smd.is_stealth_model(r)]
        self.assertEqual(len(stealth), 1)
        self.assertEqual(stealth[0]["id"], "stealth/ox-alpha")

    def test_created_date_and_pricing(self):
        rec = {"id": "stealth/x", "created": 1787256295, "pricing": {"prompt": "0", "completion": "0"}}
        d = smd.created_date(rec)
        self.assertEqual(d, "2026-08-20")
        self.assertEqual(smd.created_date({"id": "stealth/x"}), "—")  # missing created -> em dash, no crash

    def test_offline_snapshot_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            raw = pathlib.Path(td) / "raw"
            raw.mkdir(parents=True)
            old = raw / "openrouter_models_20260801.json"
            new = raw / "openrouter_models_20260810.json"
            old.write_text(json.dumps({"data": []}))
            new.write_text(json.dumps({"data": [{"id": "stealth/ox-alpha"}]}))
            # pick_latest_raw must resolve against the dir we point RAW at
            orig_raw = smd.RAW
            try:
                smd.RAW = raw
                snap = smd.pick_latest_raw("openrouter_models")
                self.assertIsNotNone(snap)
                self.assertEqual(snap.name, new.name)
                j = json.loads(snap.read_text())
                ids = [m["id"] for m in j["data"]]
                self.assertEqual(ids, ["stealth/ox-alpha"])
            finally:
                smd.RAW = orig_raw

    def test_render_cli_table(self):
        dummy_rows = [
            {
                "model_id": "stealth/ox-alpha",
                "display": "ox-alpha",
                "provider": "stealth",
                "benchmarks": {
                    "capability_q": 80.0,
                    "aa_intelligence": None,
                    "lmarena_elo": None,
                    "openrouter_context": 1048000,
                },
                "composite": None,
                "coverage": ["—"],
                "price_str": "0.00/0.00 ($0)",
                "created": "2026-08-20",
                "modality": "text->text",
            }
        ]
        tui_colored = smd.render_cli_table(dummy_rows, color=True, is_slim=False, n_aa=0, n_lm=0)
        self.assertIn("STEALTH MODEL RADAR", tui_colored)
        self.assertIn("ox-alpha", tui_colored)

        tui_plain = smd.render_cli_table(dummy_rows, color=False, is_slim=True, n_aa=0, n_lm=0)
        self.assertIn("STEALTH MODEL RADAR", tui_plain)
        self.assertIn("ox-alpha", tui_plain)

    def test_render_html(self):
        dummy_rows = [
            {
                "model_id": "test-model-1",
                "display": "test-model-1",
                "provider": "google",
                "source": "or",
                "stealth": False,
                "benchmarks": {
                    "capability_q": 85.5,
                    "p_success": 82.3,
                    "fgi_score": 63.8,
                    "aa_slug": "test-model-1",
                    "aa_intelligence": 45.0,
                    "aa_coding": 42.0,
                    "aa_agentic": 40.0,
                    "lmarena_rank": 10,
                    "lmarena_elo": 1450.0,
                    "openrouter_context": 128000,
                },
                "composite": 0.85,
                "coverage": ["AA", "LM"],
                "price_str": "0.00/0.00 ($0)",
                "created": "2026-08-20",
                "modality": "text->text",
            }
        ]
        html_s = smd.render_html(dummy_rows, 1, 1)
        self.assertIn("<!DOCTYPE html>", html_s)
        self.assertIn("test-model-1", html_s)


if __name__ == "__main__":
    unittest.main()
