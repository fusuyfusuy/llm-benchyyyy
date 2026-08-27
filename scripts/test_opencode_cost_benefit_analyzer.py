#!/usr/bin/env python3
import unittest
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import opencode_cost_benefit_analyzer as ogc
import free_model_ranker as fmc


class TestOcgoCheck(unittest.TestCase):
    def test_fallback_pricing_catalog(self):
        self.assertGreaterEqual(len(ogc.FALLBACK_PRICING), 23)
        self.assertIn("glm-5.3", ogc.FALLBACK_PRICING)
        self.assertIn("deepseek-v4-flash", ogc.FALLBACK_PRICING)
        self.assertIn("kimi-k3", ogc.FALLBACK_PRICING)
        self.assertIn("mimo-v2.5", ogc.FALLBACK_PRICING)

    def test_cost_computation(self):
        # DeepSeek V4 Flash: in 0.22, out 0.66, cached 0.007
        c = ogc.compute_cost(0.22, 0.66, 0.007, 410, 71300, 310)
        self.assertIsNotNone(c)
        self.assertGreater(c, 0.0)
        self.assertLess(c, 0.01)

    def test_snapshot_discovery(self):
        snap_aa = ogc.pick_latest_raw("artificial_analysis")
        self.assertIsNotNone(snap_aa)
        self.assertTrue(snap_aa.exists())
        snap_lm = ogc.pick_latest_raw("lmarena")
        self.assertIsNotNone(snap_lm)
        self.assertTrue(snap_lm.exists())

    def test_offline_parsing(self):
        snap_aa = ogc.pick_latest_raw("artificial_analysis")
        aa_map = ogc.parse_aa(snap_aa.read_text(errors="ignore"))
        self.assertGreater(len(aa_map), 500)

        snap_lm = ogc.pick_latest_raw("lmarena")
        lm_map = ogc.parse_lmarena(snap_lm.read_text(errors="ignore"))
        self.assertGreater(len(lm_map), 300)

        # Cross-matching
        glm_aa = ogc.find_aa_for_ocgo("glm-5.3", aa_map)
        self.assertIsNotNone(glm_aa)
        self.assertIn("intelligenceIndex", glm_aa)

        glm_lm = ogc.find_lm_for_ocgo("glm-5.3", lm_map)
        self.assertIsNotNone(glm_lm)
        self.assertIn("elo", glm_lm)

    def test_livebench_snapshot(self):
        snap_csv = ogc.RAW / "livebench_20260625.csv"
        snap_cat = ogc.RAW / "livebench_categories_20260625.json"
        self.assertTrue(snap_csv.exists())
        self.assertTrue(snap_cat.exists())
        live_map = ogc.parse_livebench(snap_csv.read_text(errors="ignore"), snap_cat.read_text(errors="ignore"))
        self.assertGreater(len(live_map), 40)
        rec = ogc.find_livebench_for_ocgo("glm-5.2", live_map)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["overall"], 73.36)

    def test_role_recommendations_in_ocheck(self):
        sample_rows = [
            {
                "model_id": "kimi-k3",
                "pricing": {"monthly_usage_limit_usd": 15},
                "caps": {"cap_5h_usd": 3.0, "cap_wk_usd": 7.5, "cap_mo_usd": 15.0},
                "cost_per_request_usd": 0.0373,
                "benchmarks": {"capability_q": 91.3, "fgi_score": 79.3, "avi_score": 226.5, "p_success": 91.0, "aa_coding": 90.0, "aa_intelligence": 92.0},
                "value": {"fgi_score": 79.3, "avi_score": 226.5, "effective_cost_per_request": 0.0373},
                "requests": {"per_5h_docs": 110},
            },
            {
                "model_id": "deepseek-v4-flash",
                "pricing": {"monthly_usage_limit_usd": 30},
                "caps": {"cap_5h_usd": 6.0, "cap_wk_usd": 15.0, "cap_mo_usd": 30.0},
                "cost_per_request_usd": 0.0014,
                "benchmarks": {"capability_q": 80.3, "fgi_score": 50.1, "avi_score": 493.9, "p_success": 73.0, "aa_coding": 82.0, "aa_intelligence": 80.0},
                "value": {"fgi_score": 50.1, "avi_score": 493.9, "effective_cost_per_request": 0.0014},
                "requests": {"per_5h_docs": 7600},
            },
        ]
        table = ogc.render_cli_table(sample_rows, color=False)
        self.assertIn("ROLE RECOMMENDATIONS", table)
        self.assertIn("Architecture", table)
    def test_catalog_diff_logic(self):
        prev_snapshot = {
            "catalog_diff": {"added": [], "removed": []},
            "models": [
                {
                    "model_id": "kimi-k3",
                    "pricing": {"monthly_usage_limit_usd": 15},
                    "value": {"fgi_score": 79.3, "avi_score": 226.5},
                    "is_docs_model": True,
                },
                {
                    "model_id": "legacy-v1",
                    "pricing": {"monthly_usage_limit_usd": 60},
                    "value": {"fgi_score": 35.0, "avi_score": 150.0},
                    "is_docs_model": True,
                },
            ],
        }
        current_rows = [
            {
                "model_id": "kimi-k3",
                "pricing": {"monthly_usage_limit_usd": 15},
                "value": {"fgi_score": 79.3, "avi_score": 226.5},
            },
            {
                "model_id": "grok-4.6",
                "pricing": {"monthly_usage_limit_usd": 15},
                "value": {"fgi_score": 75.7, "avi_score": 281.9},
            },
        ]
        diff = ogc.diff_model_catalog(current_rows, prev_snapshot)
        self.assertEqual(diff["added_ids"], {"grok-4.6"})
        self.assertEqual(diff["removed_ids"], {"legacy-v1"})
        self.assertEqual(len(diff["removed_models"]), 1)
        self.assertEqual(diff["removed_models"][0]["model_id"], "legacy-v1")

    def test_render_cli_table_diff_colors(self):
        current_rows = [
            {
                "model_id": "kimi-k3",
                "pricing": {"monthly_usage_limit_usd": 15},
                "caps": {"cap_5h_usd": 3.0, "cap_wk_usd": 7.5, "cap_mo_usd": 15.0},
                "cost_per_request_usd": 0.0373,
                "benchmarks": {"capability_q": 91.3, "fgi_score": 79.3, "avi_score": 226.5, "p_success": 91.0},
                "value": {"fgi_score": 79.3, "avi_score": 226.5, "effective_cost_per_request": 0.0373},
                "requests": {"per_5h_docs": 110},
            },
            {
                "model_id": "grok-4.6",
                "pricing": {"monthly_usage_limit_usd": 15},
                "caps": {"cap_5h_usd": 3.0, "cap_wk_usd": 7.5, "cap_mo_usd": 15.0},
                "cost_per_request_usd": 0.0224,
                "benchmarks": {"capability_q": 89.7, "fgi_score": 75.7, "avi_score": 281.9, "p_success": 89.3},
                "value": {"fgi_score": 75.7, "avi_score": 281.9, "effective_cost_per_request": 0.0224},
                "requests": {"per_5h_docs": 169},
            },
        ]
        removed_models = [
            {
                "model_id": "legacy-v1",
                "pricing": {"monthly_usage_limit_usd": 60},
                "value": {"fgi_score": 35.0, "avi_score": 150.0},
            }
        ]
        # Colored table render
        colored_table = ogc.render_cli_table(
            current_rows,
            added_ids={"grok-4.6"},
            removed_models=removed_models,
            color=True,
        )
        # Verify green color for added model
        self.assertIn("\033[38;5;48m", colored_table)
        self.assertIn("+grok-4.6", colored_table)
        self.assertIn("New (+1): grok-4.6", colored_table)
        # Verify red color for removed model
        self.assertIn("\033[38;5;196m", colored_table)
        self.assertIn("REMOVED / DEPRECATED MODELS", colored_table)
        self.assertIn("legacy-v1", colored_table)

        # Plain table render
        plain_table = ogc.render_cli_table(
            current_rows,
            added_ids={"grok-4.6"},
            removed_models=removed_models,
            color=False,
        )
        self.assertIn("+grok-4.6", plain_table)
        self.assertIn("[+NEW (+1): grok-4.6]", plain_table)
        self.assertIn("REMOVED / DEPRECATED MODELS", plain_table)
        self.assertIn("[-] legacy-v1", plain_table)

    def test_render_html_diff(self):
        current_rows = [
            {
                "model_id": "grok-4.6",
                "pricing": {"monthly_usage_limit_usd": 15},
                "caps": {"cap_5h_usd": 3.0, "cap_wk_usd": 7.5, "cap_mo_usd": 15.0},
                "cost_per_request_usd": 0.0224,
                "benchmarks": {"capability_q": 89.7, "fgi_score": 75.7, "avi_score": 281.9, "p_success": 89.3},
                "value": {"fgi_score": 75.7, "avi_score": 281.9, "effective_cost_per_request": 0.0224},
                "requests": {"per_5h_docs": 169},
            }
        ]
        removed_models = [
            {
                "model_id": "legacy-v1",
                "pricing": {"monthly_usage_limit_usd": 60},
                "value": {"fgi_score": 35.0, "avi_score": 150.0},
            }
        ]
        html = ogc.render_html(current_rows, added_ids={"grok-4.6"}, removed_models=removed_models)
        self.assertIn("badge-new", html)
        self.assertIn("+NEW", html)
        self.assertIn("removed-section", html)
        self.assertIn("legacy-v1", html)

    def test_render_limits_table(self):
        models_list = [
            {
                "model_id": "glm-5.3",
                "pricing": {"input_per_1m": 1.4, "output_per_1m": 4.4, "cached_read_per_1m": 0.26, "monthly_usage_limit_usd": 15},
                "caps": {"cap_5h_usd": 3.0, "cap_wk_usd": 7.5, "cap_mo_usd": 15.0},
                "cost_per_request_usd": 0.0152,
                "requests": {"per_5h_docs": 220, "per_week_docs": 540, "per_month_docs": 1080},
                "remaining": {"requests": {"rolling": 220, "monthly": 421}, "percent": {"rolling": 100.0, "monthly": 39.0}},
            },
            {
                "model_id": "mimo-v2.5",
                "pricing": {"input_per_1m": 0.14, "output_per_1m": 0.28, "cached_read_per_1m": 0.0028, "monthly_usage_limit_usd": 60},
                "caps": {"cap_5h_usd": 12.0, "cap_wk_usd": 30.0, "cap_mo_usd": 60.0},
                "cost_per_request_usd": 0.0004,
                "requests": {"per_5h_docs": 30100, "per_week_docs": 75200, "per_month_docs": 150400},
                "remaining": {"requests": {"rolling": 30100, "monthly": 58600}, "percent": {"rolling": 100.0, "monthly": 39.0}},
            },
        ]
        usage_percents = {"rolling": 0.0, "weekly": 23.0, "monthly": 61.0}
        usage_resets = {"rolling": "2026-08-26T21:10:00Z", "weekly": "2026-08-31T00:00:00Z", "monthly": "2026-09-19T17:43:00Z"}
        out = ogc.render_limits_table(models_list, usage_percents=usage_percents, usage_resets=usage_resets, color=False)
        self.assertIn("5h Rolling", out)
        self.assertIn("Weekly", out)
        self.assertIn("Monthly", out)
        self.assertIn("glm-5.3", out)
        self.assertIn("mimo-v2.5", out)
        self.assertIn("$15/m", out)
        self.assertIn("$60/m", out)

        # format_countdown
        c = ogc.format_countdown("2026-08-26T21:10:00Z")
        self.assertIsNotNone(c)
        self.assertNotEqual(c, "—")


class TestFreeModelsCheck(unittest.TestCase):
    def test_free_model_filter(self):
        self.assertTrue(fmc.is_free_model({"id": "google/gemma-2-9b-it:free"}))
        self.assertTrue(fmc.is_free_model({"id": "some/model", "pricing": {"prompt": "0", "completion": "0"}}))
        self.assertFalse(fmc.is_free_model({"id": "some/paid", "pricing": {"prompt": "1.5", "completion": "3.0"}}))


if __name__ == "__main__":
    unittest.main()
