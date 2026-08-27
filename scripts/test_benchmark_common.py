#!/usr/bin/env python3
import unittest
import sys
import math
import datetime as dt
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import benchmark_common as bc


class TestBenchmarkCommon(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(bc.norm_id(" Claude 3.7 Sonnet "), "claude-3.7-sonnet")
        self.assertEqual(bc.norm_id("GLM-5.3 (Thinking)"), "glm-5.3-thinking")
        self.assertEqual(bc.norm_model_slug("claude-opus-5-xhigh"), "opus-5-xhigh")
        self.assertEqual(bc.norm_model_slug("google-gemini-3.7-flash"), "gemini-3-7-flash")

    def test_safe_conversions(self):
        self.assertEqual(bc._safe_float("$1,234.56"), 1234.56)
        self.assertEqual(bc._safe_float("85.5%"), 85.5)
        self.assertIsNone(bc._safe_float("—"))
        self.assertIsNone(bc._safe_float(None))

        self.assertEqual(bc._safe_int("5,718"), 5718)
        self.assertEqual(bc._safe_int("10.0"), 10)
        self.assertIsNone(bc._safe_int("—"))

        self.assertEqual(bc._safe_int_round(4.6), 5)
        self.assertEqual(bc._safe_int_round(4.4), 4)
        self.assertIsNone(bc._safe_int_round(None))

        self.assertEqual(bc.parse_price("$0.22"), 0.22)
        self.assertIsNone(bc.parse_price("-"))

    def test_scoring_formulas_bounds_and_clamping(self):
        # Test Z-scores
        vals = [10.0, 20.0, 30.0, 40.0, 50.0]
        zs = bc.get_z_scores(vals)
        self.assertEqual(len(zs), 5)
        self.assertAlmostEqual(zs[2], 0.0, places=4)
        self.assertAlmostEqual(zs[0], -zs[4], places=4)

        # Single or empty value
        self.assertEqual(bc.get_z_scores([10.0]), [0.0])
        self.assertEqual(bc.get_z_scores([]), [])

        # Capability Q clamping
        self.assertEqual(bc.compute_capability_q(0.0), 78.0)
        self.assertGreaterEqual(bc.compute_capability_q(-10.0), 40.0)
        self.assertLessEqual(bc.compute_capability_q(10.0), 99.9)

        # Pass rate P_succ sigmoid
        p72 = bc.compute_p_success(72.0)
        self.assertAlmostEqual(p72, 50.0, places=1)
        p_high = bc.compute_p_success(95.0)
        self.assertGreater(p_high, 90.0)
        p_low = bc.compute_p_success(50.0)
        self.assertLess(p_low, 10.0)

        # Token multiplier
        t_mult_100 = bc.compute_token_multiplier(100.0)
        self.assertAlmostEqual(t_mult_100, 1.0, places=2)
        t_mult_50 = bc.compute_token_multiplier(50.0)
        self.assertAlmostEqual(t_mult_50, 3.2, places=1) # (1 + 1.2*0.5)/0.5 = 1.6/0.5 = 3.2
        t_mult_low = bc.compute_token_multiplier(2.0)
        self.assertGreater(t_mult_low, 50.0)

        # Effective cost
        eff_cost = bc.compute_effective_cost(2.0, 3.2)
        self.assertEqual(eff_cost, 6.4)

        # Value indices
        avi = bc.compute_avi(85.0, 5.0)
        self.assertGreater(avi, 0.0)

        fgi = bc.compute_fgi(90.0, 95.0)
        self.assertGreater(fgi, 0.0)

        bfi = bc.compute_bfi(80.0, 100.0, 0.5)
        self.assertGreater(bfi, 0.0)

    def test_display_helpers(self):
        text = f"{bc.C_BOLD}{bc.C_GREEN}Hello World{bc.C_RESET}"
        self.assertEqual(bc.display_len(text), 11)

        cell = bc.color_cell("Test", bc.C_CYAN, width=10, align="<")
        self.assertEqual(bc.display_len(cell), 12) # 10 padded + 2 internal padding

        self.assertEqual(bc.medal_badge(1, color=False), "¹")
        self.assertEqual(bc.medal_badge(2, color=False), "²")
        self.assertEqual(bc.medal_badge(3, color=False), "³")
        self.assertEqual(bc.medal_badge(None, color=False), "")

        self.assertEqual(bc.pool_badge("claude", color=False), "[CLD]")
        self.assertEqual(bc.pool_badge("agy", color=False), "[AGY]")
        self.assertEqual(bc.pool_badge("ocgo", color=False), "[OCG]")
        self.assertEqual(bc.pool_badge("or", color=False), "[OR]")
        self.assertEqual(bc.pool_badge("cline", color=False), "[CLN]")
        self.assertEqual(bc.pool_badge("cln", color=False), "[CLN]")

    def test_parsers_synthetic(self):
        # Test LiveBench
        sample_csv = "model,coding,reasoning\ngemini-3.7-flash,85.0,90.0\n"
        lb = bc.parse_livebench(sample_csv)
        self.assertIn("gemini-3.7-flash", lb)
        self.assertEqual(lb["gemini-3.7-flash"]["overall"], 87.5)

        # Test LMArena
        sample_html = """
        <table>
          <tr><th>Rank</th><th>Icon</th><th>Model</th><th>Score</th><th>Votes</th><th>Price</th><th>Context</th></tr>
          <tr><td>1</td><td>icon</td><td title="claude-opus-5">Claude Opus 5</td><td>1520±5</td><td>10,000</td><td>$5 / $25</td><td>200k</td></tr>
        </table>
        """
        lm = bc.parse_lmarena(sample_html)
        self.assertIn("claude-opus-5", lm)
        self.assertEqual(lm["claude-opus-5"]["elo"], 1520.0)
        self.assertEqual(lm["claude-opus-5"]["rank"], 1)

        # Test OpenRouter
        sample_or = {
            "data": [
                {"id": "anthropic/claude-3.7-sonnet", "name": "Claude 3.7", "pricing": {"prompt": "0.000003", "completion": "0.000015"}, "context_length": 200000},
                {"id": "meta/llama-3-8b:free", "name": "Llama 3 8B Free", "pricing": {"prompt": "0", "completion": "0"}, "context_length": 8000}
            ]
        }
        or_map = bc.parse_openrouter(sample_or)
        self.assertIn("anthropic/claude-3.7-sonnet", or_map)
        self.assertFalse(or_map["anthropic/claude-3.7-sonnet"]["is_free"])
        self.assertTrue(or_map["meta/llama-3-8b:free"]["is_free"])

    def test_role_recommendations_calculation(self):
        sample_models = [
            {"display": "Claude Fable 5 (High)", "pool": "claude", "capability_q": 89.4, "fgi_score": 75.1, "avi_score": 141.6, "bfi_score": 120.0, "p_success": 89.0, "effective_cost": 22.86, "base_metrics": {"lm_coding": 1508, "speed_tps": 35}},
            {"display": "DeepSeek V4 Flash", "pool": "ocgo", "capability_q": 73.4, "fgi_score": 29.3, "avi_score": 552.0, "bfi_score": 450.0, "p_success": 54.2, "effective_cost": 0.20, "base_metrics": {"lm_coding": 1436, "speed_tps": 95}},
            {"display": "MiMo-V2.5", "pool": "ocgo", "capability_q": 69.2, "fgi_score": 18.6, "avi_score": 328.2, "bfi_score": 520.0, "p_success": 41.7, "effective_cost": 0.69, "base_metrics": {"lm_coding": 1434, "speed_tps": 115}},
        ]
        recs = bc.compute_role_recommendations(sample_models, context="bcheck")
        self.assertIn("architecture", recs)
        self.assertIn("pair_programming", recs)
        self.assertIn("daily_driver", recs)
        self.assertIn("boilerplate", recs)

        # Architecture should prefer high FGI / Q model (Claude Fable 5)
        self.assertEqual(recs["architecture"]["winner"]["name"], "Claude Fable 5")
        
        # Daily Driver should prefer highest AVI / Cost-efficiency model (DeepSeek V4 Flash)
        self.assertEqual(recs["daily_driver"]["winner"]["name"], "DeepSeek V4 Flash")

        # Test CLI renderer
        cli_lines = bc.render_role_recommendations_cli(recs, color=False)
        self.assertGreaterEqual(len(cli_lines), 8)
        self.assertIn("Architecture", "".join(cli_lines))
        self.assertIn("Daily Driver", "".join(cli_lines))

        # Test Markdown renderer
        md_text = bc.render_role_recommendations_md(recs)
        self.assertIn("### Dynamic Function & Role Recommendations", md_text)
        self.assertIn("Claude Fable 5", md_text)

        # Test HTML renderer
        html_text = bc.render_role_recommendations_html(recs)
        self.assertIn("Dynamic Function & Role Recommendations", html_text)
        self.assertIn("Claude Fable 5", html_text)

    def test_catalog_diff_and_removed_models(self):
        # 1. Snapshot as list
        prev_list = [
            {"display": "Claude 3.5 Sonnet", "pool": "claude", "fgi_score": 55.0, "avi_score": 180.0},
            {"display": "GPT-4o", "pool": "frontier", "fgi_score": 50.0, "avi_score": 200.0},
        ]
        curr_list = [
            {"display": "Claude 3.5 Sonnet", "pool": "claude", "fgi_score": 55.0, "avi_score": 180.0},
            {"display": "Claude 3.7 Sonnet", "pool": "claude", "fgi_score": 68.0, "avi_score": 240.0},
        ]
        diff = bc.diff_model_catalog(curr_list, prev_list, id_key="display")
        self.assertEqual(diff["added_ids"], {"Claude 3.7 Sonnet"})
        self.assertEqual(diff["removed_ids"], {"GPT-4o"})
        self.assertEqual(len(diff["removed_models"]), 1)
        self.assertEqual(diff["removed_models"][0]["display"], "GPT-4o")

        # 2. Snapshot as dict with 'models'
        prev_dict = {
            "models": [
                {"model_id": "mimo-v2", "pricing": {"monthly_usage_limit_usd": 60}},
                {"model_id": "glm-5", "pricing": {"monthly_usage_limit_usd": 15}},
            ]
        }
        curr_dict_rows = [
            {"model_id": "glm-5", "pricing": {"monthly_usage_limit_usd": 15}},
            {"model_id": "glm-5.3", "pricing": {"monthly_usage_limit_usd": 15}},
        ]
        diff2 = bc.diff_model_catalog(curr_dict_rows, prev_dict, id_key="model_id")
        self.assertEqual(diff2["added_ids"], {"glm-5.3"})
        self.assertEqual(diff2["removed_ids"], {"mimo-v2"})
        self.assertEqual(len(diff2["removed_models"]), 1)

        # 3. Test render_removed_models_cli
        rem_color = bc.render_removed_models_cli(diff["removed_models"], color=True, id_key="display")
        self.assertIn("\033[38;5;196m", "".join(rem_color))
        self.assertIn("GPT-4o", "".join(rem_color))

        rem_plain = bc.render_removed_models_cli(diff["removed_models"], color=False, id_key="display")
        self.assertIn("[-] GPT-4o", "".join(rem_plain))

    def test_first_seen_window_and_timestamp_persistence(self):
        # 1. Test parse_timestamp
        t1 = bc.parse_timestamp("2026-08-20T12:00:00Z")
        self.assertIsNotNone(t1)
        self.assertEqual(t1.year, 2026)
        self.assertEqual(t1.month, 8)
        self.assertEqual(t1.day, 20)

        # Epoch seconds & ms
        t2 = bc.parse_timestamp(1724500000)
        self.assertIsNotNone(t2)
        t3 = bc.parse_timestamp(1724500000000)
        self.assertIsNotNone(t3)
        self.assertEqual(t2, t3)

        # 2. Multi-run simulation with 7-day window
        base_time = dt.datetime(2026, 8, 26, 12, 0, 0, tzinfo=dt.timezone.utc)
        
        # Initial snapshot on Day 0 (Aug 20, 2026 - 6 days ago)
        prev_snapshot = {
            "models": [
                {"model_id": "old-model", "first_seen": "2026-08-10T12:00:00+00:00"},
                {"model_id": "fresh-model", "first_seen": "2026-08-22T12:00:00+00:00"}, # 4 days old
            ]
        }

        # Current rows on Aug 26, 2026:
        # - old-model: 16 days old (> 7d, normal)
        # - fresh-model: 4 days old (<= 7d, green)
        # - brand-new-model: unseen in prev_snapshot (0 days old, green)
        current_rows = [
            {"model_id": "old-model"},
            {"model_id": "fresh-model"},
            {"model_id": "brand-new-model"},
        ]

        # Run 1
        diff1 = bc.diff_model_catalog(current_rows, prev_snapshot, id_key="model_id", window_days=7.0, now=base_time)
        self.assertIn("fresh-model", diff1["added_ids"])
        self.assertIn("brand-new-model", diff1["added_ids"])
        self.assertNotIn("old-model", diff1["added_ids"])
        self.assertEqual(current_rows[2]["first_seen"], base_time.isoformat())

        # Simulate Run 2 (5 minutes later): current_rows from Run 1 are saved and re-loaded
        simulated_saved_snapshot = {"models": current_rows}
        current_rows_run2 = [
            {"model_id": "old-model"},
            {"model_id": "fresh-model"},
            {"model_id": "brand-new-model"},
        ]
        diff2 = bc.diff_model_catalog(current_rows_run2, simulated_saved_snapshot, id_key="model_id", window_days=7.0, now=base_time + dt.timedelta(minutes=5))
        # Both fresh-model and brand-new-model must STILL be green!
        self.assertIn("fresh-model", diff2["added_ids"])
        self.assertIn("brand-new-model", diff2["added_ids"])
        self.assertNotIn("old-model", diff2["added_ids"])

        # Simulate Run 3 (8 days later): brand-new-model is now 8 days old (> 7d)
        future_time = base_time + dt.timedelta(days=8)
        current_rows_run3 = [
            {"model_id": "old-model"},
            {"model_id": "fresh-model"},
            {"model_id": "brand-new-model"},
        ]
        diff3 = bc.diff_model_catalog(current_rows_run3, simulated_saved_snapshot, id_key="model_id", window_days=7.0, now=future_time)
        # All models have aged past 7 days -> no longer green
        self.assertNotIn("brand-new-model", diff3["added_ids"])
        self.assertNotIn("fresh-model", diff3["added_ids"])
        self.assertNotIn("old-model", diff3["added_ids"])
        self.assertEqual(len(diff3["added_ids"]), 0)


if __name__ == "__main__":
    unittest.main()
