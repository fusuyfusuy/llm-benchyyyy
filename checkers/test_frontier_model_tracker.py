#!/usr/bin/env python3
"""
test_frontier_model_tracker.py — Unit tests for frontier model tracker (OpenAI, Claude, Gemini)
"""
import json
import pathlib
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import frontier_model_tracker as fmt


class TestFrontierModelTracker(unittest.TestCase):
    def test_load_openrouter_pricing_map(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raw = pathlib.Path(tmpdir)
            mock_data = {
                "data": [
                    {
                        "id": "anthropic/claude-opus-5",
                        "name": "Claude Opus 5",
                        "pricing": {"prompt": "0.000005", "completion": "0.000025", "input_cache_read": "0.0000005"},
                        "context_length": 1000000,
                    },
                    {
                        "id": "openai/gpt-6-astra",
                        "name": "GPT-6 Astra",
                        "pricing": {"prompt": "0.00001", "completion": "0.00005", "input_cache_read": "0.000001"},
                        "context_length": 1050000,
                    },
                ]
            }
            (raw / "openrouter_models_20260916.json").write_text(json.dumps(mock_data))
            pricing = fmt.load_openrouter_pricing_map(raw)
            self.assertIn("anthropic/claude-opus-5", pricing)
            self.assertIn("claude-opus-5", pricing)
            self.assertEqual(pricing["claude-opus-5"]["price_in"], 5.0)
            self.assertEqual(pricing["claude-opus-5"]["price_out"], 25.0)
            self.assertEqual(pricing["claude-opus-5"]["price_cache"], 0.5)
            self.assertEqual(pricing["claude-opus-5"]["context_length"], 1000000)

    def test_find_model_pricing(self):
        pricing_map = {
            "claude-opus-5": {"id": "anthropic/claude-opus-5", "price_in": 5.0, "price_out": 25.0},
            "gpt-5.6-sol": {"id": "openai/gpt-5.6-sol", "price_in": 2.0, "price_out": 10.0},
            "gemini-3.8-flash": {"id": "google/gemini-3.8-flash", "price_in": 0.75, "price_out": 3.75},
        }
        # Parentheses removal
        m1 = fmt.find_model_pricing("Claude Opus 5 (Thinking)", pricing_map)
        self.assertIsNotNone(m1)
        self.assertEqual(m1["id"], "anthropic/claude-opus-5")

        # Hyphen/tier suffix removal
        m2 = fmt.find_model_pricing("GPT-5.6 Sol (Reasoning)", pricing_map)
        self.assertIsNotNone(m2)
        self.assertEqual(m2["id"], "openai/gpt-5.6-sol")

        # Direct match
        m3 = fmt.find_model_pricing("Gemini 3.8 Flash", pricing_map)
        self.assertIsNotNone(m3)
        self.assertEqual(m3["id"], "google/gemini-3.8-flash")

    def test_extract_and_save_frontier_models(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p_tmp = pathlib.Path(tmpdir)
            bench = {
                "models": [
                    {
                        "display": "Claude Opus 5 (Thinking)",
                        "livebench": {"overall": 80.5},
                        "aa_live_quality": 50.7,
                        "base_metrics": {"lm_elo": 1660},
                    },
                    {
                        "display": "GPT-6 Astra (xhigh)",
                        "livebench": {"overall": 83.0},
                        "aa_live_quality": 52.5,
                        "base_metrics": {"lm_elo": 1800},
                    },
                    {
                        "display": "Gemini 3.8 Flash",
                        "livebench": {"overall": 77.5},
                        "aa_live_quality": 41.2,
                        "base_metrics": {"lm_elo": 1568},
                    },
                ]
            }
            bench_path = p_tmp / "benchmarks.json"
            bench_path.write_text(json.dumps(bench))

            raw_path = p_tmp / "raw"
            raw_path.mkdir()
            mock_or = {
                "data": [
                    {"id": "anthropic/claude-opus-5", "pricing": {"prompt": "0.000005", "completion": "0.000025"}, "context_length": 1000000},
                    {"id": "openai/gpt-6-astra", "pricing": {"prompt": "0.00001", "completion": "0.00005"}, "context_length": 1050000},
                    {"id": "google/gemini-3.8-flash", "pricing": {"prompt": "0.00000075", "completion": "0.00000375"}, "context_length": 1048576},
                ]
            }
            (raw_path / "openrouter_models_20260916.json").write_text(json.dumps(mock_or))

            payload = fmt.extract_frontier_models(bench_path=bench_path, raw_dir=raw_path)
            self.assertIn("providers", payload)
            self.assertIn("claude", payload["providers"])
            self.assertIn("openai", payload["providers"])
            self.assertIn("gemini", payload["providers"])

            self.assertEqual(payload.get("pricing_standard"), "USD per 1M tokens ($/1M)")
            self.assertEqual(payload.get("unit"), "USD / 1M tokens")
            claude_data = payload["providers"]["claude"]
            self.assertEqual(claude_data["total_tracked"], 1)
            self.assertEqual(claude_data["with_pricing"], 1)
            self.assertEqual(claude_data["models"][0]["pricing"]["unit"], "USD / 1M tokens")
            self.assertEqual(claude_data["models"][0]["pricing"]["input_per_1m"], 5.0)
            self.assertEqual(claude_data["models"][0]["pricing"]["price_in_1m"], 5.0)

            out_file = p_tmp / "frontier_models.json"
            saved_p = fmt.save_frontier_models(payload, out_path=out_file)
            self.assertTrue(saved_p.exists())
            loaded = json.loads(saved_p.read_text())
            self.assertIn("claude", loaded["providers"])
            self.assertEqual(loaded.get("pricing_standard"), "USD per 1M tokens ($/1M)")


if __name__ == "__main__":
    unittest.main()
