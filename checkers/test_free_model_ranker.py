#!/usr/bin/env python3
"""Unit tests for free_model_ranker.py (fcheck)."""
import unittest
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import free_model_ranker as fmr


class TestFreeModelRanker(unittest.TestCase):
    def test_is_free_model(self):
        self.assertTrue(fmr.is_free_model({"id": "meta-llama/llama-3-8b:free", "pricing": {"prompt": "0", "completion": "0"}}))
        self.assertTrue(fmr.is_free_model({"id": "meta-llama/llama-3-8b", "pricing": {"prompt": "0", "completion": "0"}}))
        self.assertTrue(fmr.is_free_model({"id": "custom/free-model:free", "pricing": {}}))
        self.assertFalse(fmr.is_free_model({"id": "openai/gpt-4o", "pricing": {"prompt": "2.5", "completion": "10.0"}}))
        self.assertFalse(fmr.is_free_model({"id": "unknown", "pricing": {}}))
        self.assertFalse(fmr.is_free_model({"id": "unknown"}))
        self.assertFalse(fmr.is_free_model({"id": "sentinel", "pricing": {"prompt": "-1", "completion": "-1"}}))

    def test_render_cli_table(self):
        dummy_rows = [
            {
                "model_id": "test-model-1",
                "display": "test-model-1",
                "provider": "cline",
                "source": "cln",
                "stealth": False,
                "benchmarks": {
                    "capability_q": 85.5,
                    "p_success": 82.3,
                    "fgi_score": 63.8,
                    "aa_intelligence": 45.0,
                    "lmarena_elo": 1450.0,
                    "openrouter_context": 128000,
                },
                "composite": 0.85,
                "coverage": ["AA", "LM"],
            }
        ]
        tui_colored = fmr.render_cli_table(dummy_rows, color=True, is_slim=False, n_aa=1, n_lm=1)
        self.assertIn("FREE MODEL RADAR", tui_colored)
        self.assertIn("test-model-1", tui_colored)
        self.assertIn("🥇#1", tui_colored)

        tui_plain = fmr.render_cli_table(dummy_rows, color=False, is_slim=True, n_aa=1, n_lm=1)
        self.assertIn("FREE MODEL RADAR", tui_plain)
        self.assertIn("test-model-1", tui_plain)

    def test_render_html(self):
        dummy_rows = [
            {
                "model_id": "test-model-1",
                "display": "test-model-1",
                "provider": "cline",
                "source": "cln",
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
        html_f = fmr.render_html(dummy_rows, 1, 1)
        self.assertIn("<!DOCTYPE html>", html_f)
        self.assertIn("test-model-1", html_f)

    def test_catalog_diff(self):
        dummy_rows = [
            {
                "model_id": "cline-free/gemma-3",
                "display": "gemma-3",
                "provider": "cline",
                "source": "cln",
                "stealth": False,
                "benchmarks": {
                    "capability_q": 85.5,
                    "p_success": 82.3,
                    "fgi_score": 63.8,
                    "aa_intelligence": 45.0,
                    "lmarena_elo": 1450.0,
                    "openrouter_context": 128000,
                },
                "composite": 0.85,
                "coverage": ["AA", "LM"],
            }
        ]
        removed_models = [
            {
                "model_id": "old/legacy-model:free",
                "display": "legacy-model",
                "provider": "old-prov",
                "benchmarks": {"capability_q": 55.0},
            }
        ]
        # Colored CLI table
        tui_colored = fmr.render_cli_table(
            dummy_rows,
            color=True,
            added_ids={"cline-free/gemma-3"},
            removed_models=removed_models,
        )
        self.assertIn("\033[38;5;48m", tui_colored)
        self.assertIn("+gemma-3", tui_colored)
        self.assertIn("New (+1): cline-free/gemma-3", tui_colored)
        self.assertIn("\033[38;5;196m", tui_colored)
        self.assertIn("REMOVED / DEPRECATED MODELS", tui_colored)
        self.assertIn("legacy-model", tui_colored)

        # Plain CLI table
        tui_plain = fmr.render_cli_table(
            dummy_rows,
            color=False,
            added_ids={"cline-free/gemma-3"},
            removed_models=removed_models,
        )
        self.assertIn("+gemma-3", tui_plain)
        self.assertIn("[+NEW (+1): cline-free/gemma-3]", tui_plain)
        self.assertIn("[-] legacy-model", tui_plain)

        # HTML
        html_text = fmr.render_html(
            dummy_rows,
            1,
            1,
            added_ids={"cline-free/gemma-3"},
            removed_models=removed_models,
        )
        self.assertIn("badge-new", html_text)
        self.assertIn("+NEW", html_text)
        self.assertIn("removed-section", html_text)
        self.assertIn("legacy-model", html_text)

    def test_base_id_normalization(self):
        self.assertEqual(fmr.base_id("meta-llama/llama-3-8b:free"), "meta-llama/llama-3-8b")
        self.assertEqual(fmr.base_id("deepseek-v4-flash-free"), "deepseek-v4-flash")
        self.assertEqual(fmr.base_id("mimo-v2.5-free"), "mimo-v2.5")
        self.assertEqual(fmr.base_id("claude-opus-5"), "claude-opus-5")

    def test_multi_source_rendering(self):
        multi_rows = [
            {
                "model_id": "claude-opus-5",
                "display": "claude-opus-5",
                "provider": "cline",
                "source": "cln",
                "stealth": False,
                "benchmarks": {"capability_q": 92.0, "p_success": 91.0, "fgi_score": 80.0, "aa_intelligence": 50.0, "lmarena_elo": 1500.0, "openrouter_context": None},
                "composite": 1.5,
                "coverage": ["AA", "LM"],
            },
            {
                "model_id": "deepseek-v4-flash-free",
                "display": "deepseek-v4-flash",
                "provider": "opencode",
                "source": "oc",
                "stealth": False,
                "benchmarks": {"capability_q": 85.0, "p_success": 82.0, "fgi_score": 65.0, "aa_intelligence": 44.0, "lmarena_elo": 1440.0, "openrouter_context": None},
                "composite": 0.8,
                "coverage": ["AA", "LM"],
            },
            {
                "model_id": "opencode/big-pickle",
                "display": "big-pickle",
                "provider": "opencode",
                "source": "oc",
                "stealth": True,
                "benchmarks": {"capability_q": 80.0, "p_success": 75.0, "fgi_score": 55.0, "aa_intelligence": 40.0, "lmarena_elo": 1420.0, "openrouter_context": 128000},
                "composite": 0.5,
                "coverage": ["AA", "LM"],
            },
        ]
        # CLI plain
        cli_plain = fmr.render_cli_table(multi_rows, color=False, is_slim=False, n_aa=3, n_lm=3)
        self.assertIn("[CLN]", cli_plain)
        self.assertIn("[OC]", cli_plain)
        self.assertIn("[STL]", cli_plain)
        self.assertIn("FREE MODEL RADAR (OpenCode Zen/Go + Cline)", cli_plain)
        self.assertNotIn("[OR]", cli_plain)

        # HTML
        html_out = fmr.render_html(multi_rows, 3, 3)
        self.assertIn("badge-cln", html_out)
        self.assertIn("badge-ocg", html_out)
        self.assertIn("Free Models (OpenCode Zen/Go + Cline)", html_out)
        self.assertNotIn('class="badge badge-or"', html_out)

    def test_openrouter_models_not_listed(self):
        # Scope cut 2026-08-30: listed rows are OpenCode Zen/Go + Cline only.
        # A plain offline end-to-end run must not emit a single [OR] badge.
        import subprocess
        r = subprocess.run(
            [sys.executable, str(HERE / "free_model_ranker.py"), "--check", "--plain"],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        self.assertIn("not listed", r.stdout)
        self.assertNotIn("[OR]", r.stdout)
        self.assertTrue("[OC]" in r.stdout or "[CLN]" in r.stdout)

    def test_cached_json_loader_is_offline_by_default(self):
        # rule 7 / S3-F3-5: plain call must read the cache, never touch network
        data = fmr.fetch_or_load_cached_json(
            fmr.CLINE_RECOMMENDED_MODELS_API,
            "cline_models",
            verbose=False,
        )
        self.assertIsNotNone(data)
        self.assertTrue("free" in data or "data" in data)
        free_list = data.get("free", data.get("data", []))
        self.assertGreaterEqual(len(free_list), 1)

    def test_free_key_dedups_provider_prefix(self):
        # S3-F3-3: the same free model on two platforms must collapse to one key
        self.assertEqual(fmr._free_key("nemotron-3.5-lightning-free"), fmr._free_key("nvidia/nemotron-3.5-lightning:free"))
        self.assertEqual(fmr._free_key("deepseek-v4-flash-free"), fmr._free_key("deepseek/deepseek-v4-flash"))
        self.assertEqual(fmr._free_key("laguna-s-2.1-free"), fmr._free_key("poolside/laguna-s-2.1:free"))
        # distinct models must NOT collapse
        self.assertNotEqual(fmr._free_key("nemotron-3.5-lightning-free"), fmr._free_key("deepseek-v4-flash-free"))


if __name__ == "__main__":
    unittest.main()
