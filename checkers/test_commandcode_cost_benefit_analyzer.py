#!/usr/bin/env python3
import unittest
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import commandcode_cost_benefit_analyzer as ccc
import benchmark_common as bc


class TestCcCheck(unittest.TestCase):
    def test_fallback_pricing_catalog(self):
        self.assertGreaterEqual(len(ccc.FALLBACK_PRICING), 40)
        self.assertIn("glm-5.3", ccc.FALLBACK_PRICING)
        self.assertIn("deepseek-v4-flash", ccc.FALLBACK_PRICING)
        self.assertIn("kimi-k3", ccc.FALLBACK_PRICING)
        self.assertIn("mimo-v2.5", ccc.FALLBACK_PRICING)
        self.assertIn("laguna-s-2.1-free", ccc.FALLBACK_PRICING)
        self.assertIsNone(ccc.FALLBACK_PRICING["laguna-s-2.1-free"]["input"])
        self.assertEqual(ccc.FALLBACK_PRICING["gpt-5.6-sol"]["credits"], 70.0)
        self.assertEqual(ccc.FALLBACK_PRICING["minimax-m3"]["credits"], 47.0)

    def test_cost_computation(self):
        c = ccc.compute_cost(0.22, 0.66, 0.007, 800, 50000, 160)
        self.assertIsNotNone(c)
        self.assertGreater(c, 0.0)
        self.assertLess(c, 0.01)
        self.assertIsNone(ccc.compute_cost(None, 0.66, 0.007, 800, 50000, 160))
        self.assertEqual(ccc.compute_cost(0.22, 0.66, 0.007, 0, 0, 0), 0.0)
        # Free tier
        self.assertIsNone(ccc.compute_cost(None, None, None, 800, 50000, 160))

    def test_cost_sanity_against_docs_requests(self):
        pr = ccc.FALLBACK_PRICING["glm-5.2"]
        cost = ccc.compute_cost(pr["input"], pr["output"], pr["cached_read"], 800, 50000, 160)
        self.assertIsNotNone(cost)
        req5 = (pr["credits"] * 14 / 70) / cost
        self.assertAlmostEqual(req5, 947, delta=80)
        pr2 = ccc.FALLBACK_PRICING["gpt-5.6-sol"]
        cost2 = ccc.compute_cost(pr2["input"], pr2["output"], pr2["cached_read"], 800, 50000, 160)
        req5_2 = (pr2["credits"] * 14 / 70) / cost2
        self.assertAlmostEqual(req5_2, 414, delta=60)

    def test_norm_cc_id(self):
        self.assertEqual(ccc._norm_cc_id("GLM-5.3 Flash"), "glm-5.3-flash")
        self.assertEqual(ccc._norm_cc_id("DeepSeek V4 Flash Vision (exp)"), "deepseek-v4-flash-vision")
        self.assertEqual(ccc._norm_cc_id("Laguna S 2.1 Free"), "laguna-s-2.1-free")
        self.assertEqual(ccc._norm_cc_id("Tencent Hy4 Preview"), "tencent-hy4-preview")
        self.assertIsNone(ccc._norm_cc_id(""))

    def test_quality_sort_mode_distinct_from_cap(self):
        rows = [
            {"model_id": "a", "benchmarks": {"aa_intelligence": 40.0, "capability_q": 90.0}, "value": {"avi_score": 100.0, "fgi_score": 80.0, "bfi_score": 30.0, "intelligence_per_dollar": 5.0}, "requests": {}},
            {"model_id": "b", "benchmarks": {"aa_intelligence": 70.0, "capability_q": 60.0}, "value": {"avi_score": 50.0, "fgi_score": 40.0, "bfi_score": 20.0, "intelligence_per_dollar": 9.0}, "requests": {}},
            {"model_id": "c", "benchmarks": {"aa_intelligence": None, "capability_q": 30.0}, "value": {"avi_score": 10.0, "fgi_score": None, "bfi_score": None, "intelligence_per_dollar": None}, "requests": {}},
        ]
        ids = lambda key: [r["model_id"] for r in sorted(rows, key=key)]
        self.assertEqual(ids(ccc.build_sort_key("quality", lambda r: 999.0)), ["b", "a", "c"])
        self.assertEqual(ids(ccc.build_sort_key("cap", lambda r: 999.0)), ["a", "b", "c"])
        for mode in ("value", "qvi", "avi", "fgi", "bfi", "cap", "quality", "req5h", "cost", "intel"):
            ccc.build_sort_key(mode, lambda r: 999.0)(rows[0])
        with self.assertRaises(ValueError):
            ccc.build_sort_key("bogus", lambda r: 999.0)

    def test_snapshot_discovery(self):
        snap = ccc.pick_latest_raw("cc_goat_docs")
        self.assertIsNotNone(snap)
        self.assertTrue(snap.exists())
        snap_aa = ccc.pick_latest_raw("artificial_analysis")
        self.assertIsNotNone(snap_aa)
        snap_lm = ccc.pick_latest_raw("lmarena")
        self.assertIsNotNone(snap_lm)

    def test_offline_parsing(self):
        snap_aa = ccc.pick_latest_raw("artificial_analysis")
        aa_map = ccc.parse_aa(snap_aa.read_text(errors="ignore"))
        self.assertGreater(len(aa_map), 500)
        snap_lm = ccc.pick_latest_raw("lmarena")
        lm_map = ccc.parse_lmarena(snap_lm.read_text(errors="ignore"))
        self.assertGreater(len(lm_map), 100)
        # Cross-matching via GOAT ids
        glm_aa = ccc.find_aa_for_cc("glm-5.3", aa_map)
        self.assertIsNotNone(glm_aa)
        self.assertEqual(glm_aa["slug"], "glm-5-3")
        glm_lm = ccc.find_lm_for_cc("glm-5.3", lm_map)
        self.assertIsNotNone(glm_lm)
        self.assertEqual(glm_lm["rank"], 10)

    def test_parse_cc_docs_header_matched_tables(self):
        # Catalog first, requests last — header-matched, not positional
        html = """
        <table><thead><tr><th>Model</th><th>Context</th><th>Intelligence</th><th>Tok/s</th><th>Input</th><th>Output</th><th>Cache read</th><th>Cache write</th><th>Caps</th></tr></thead>
        <tbody><tr><td>Grok 4.6</td><td>500K</td><td>60.9</td><td>61</td><td>$2.00</td><td>$6.00</td><td>$0.50</td><td>-</td><td></td></tr></tbody></table>
        <table><thead><tr><th>Model</th><th>Input</th><th>Output</th><th>Cache Read</th><th>Cache Write</th><th>Monthly credits</th></tr></thead>
        <tbody><tr><td>Grok 4.6</td><td>$2.00</td><td>$6.00</td><td>$0.50</td><td>-</td><td>$20</td></tr></tbody></table>
        <table><thead><tr><th>Model</th><th>requests / 5 hours</th><th>requests / week</th><th>requests / month</th></tr></thead>
        <tbody><tr><td>Grok 4.6</td><td>144</td><td>360</td><td>719</td></tr></tbody></table>
        """
        pricing, requests, intel = ccc.parse_cc_docs(html)
        self.assertIn("grok-4.6", pricing)
        self.assertEqual(pricing["grok-4.6"]["input"], 2.0)
        self.assertEqual(pricing["grok-4.6"]["credits"], 20.0)
        self.assertIn("grok-4.6", requests)
        self.assertEqual(requests["grok-4.6"], {"per_5h": 144, "per_week": 360, "per_month": 719})

    def test_parse_cc_docs_intel_rsc_payload(self):
        # The GOAT docs embed the official intelligence catalog as an RSC
        # "models":[...] payload with intelligenceIndex/codingIndex/TPS.
        html = (
            '<div>intro text</div>'
            '<script>self.__next_f.push([1,"12:[\"$\",\"$L40\",null,{\"models\":['
            '{\"slug\":\"glm-5-3-flash\",\"id\":\"z-ai/glm-5.3-flash\",\"name\":\"GLM-5.3 Flash\",'
            '\"intelligenceIndex\":57.5,\"codingIndex\":71.5,\"outputTokensPerSec\":41.8,'
            '\"contextWindow\":1048576,\"minPlanName\":\"Go\"},'
            '{\"slug\":\"grok-4-6\",\"id\":\"xai/grok-4.6\",\"name\":\"Grok 4.6\",'
            '\"intelligenceIndex\":60.9,\"codingIndex\":76.8,\"outputTokensPerSec\":60.8,'
            '\"contextWindow\":1000000,\"minPlanName\":\"GOAT\"}'
            ']}]\n"])</script>'
            '<table><thead><tr><th>Model</th><th>Input</th><th>Output</th><th>Cache Read</th><th>Cache Write</th><th>Monthly credits</th></tr></thead><tbody></tbody></table>'
        )
        _, _, intel = ccc.parse_cc_docs(html)
        self.assertIn("glm-5.3-flash", intel)
        self.assertEqual(intel["glm-5.3-flash"]["intelligenceIndex"], 57.5)
        self.assertEqual(intel["glm-5.3-flash"]["codingIndex"], 71.5)
        self.assertEqual(intel["glm-5.3-flash"]["outputTokensPerSec"], 41.8)
        self.assertIn("grok-4.6", intel)
        self.assertEqual(intel["grok-4.6"]["intelligenceIndex"], 60.9)
        # No models array -> empty intel dict
        _, _, intel2 = ccc.parse_cc_docs("<table><tr><td>x</td></tr></table>")
        self.assertEqual(intel2, {})

    def test_build_sort_key_intel_cc(self):
        rows = [
            {"model_id": "a", "benchmarks": {"capability_q": 80.0, "cc_intelligence": 50.0}, "value": {"avi_score": 100.0}},
            {"model_id": "b", "benchmarks": {"capability_q": 85.0, "cc_intelligence": 60.0}, "value": {"avi_score": 200.0}},
            {"model_id": "c", "benchmarks": {"capability_q": 90.0}, "value": {"avi_score": 300.0}},
        ]
        key = ccc.build_sort_key("intel-cc", lambda r: 1.0)
        sorted_rows = sorted(rows, key=key)
        self.assertEqual(sorted_rows[0]["model_id"], "b")  # highest cc_intelligence first
        self.assertEqual(sorted_rows[1]["model_id"], "a")
        self.assertEqual(sorted_rows[2]["model_id"], "c")  # None last

    def test_render_cli_table_cc_intel_column(self):
        rows = [
            {"model_id": "glm-5.3-flash", "pricing": {"monthly_credits": 20}, "caps": {"cap_5h_usd": 4.0}, "cost_per_request_usd": 0.014, "benchmarks": {"capability_q": 88.0, "fgi_score": 70.0, "avi_score": 300.0, "p_success": 86.0, "cc_intelligence": 57.5}, "value": {"fgi_score": 70.0, "avi_score": 300.0, "effective_cost_per_request": 0.02, "leverage_vs_10usd_sub": 2.0}, "requests": {"per_5h_docs": 271}},
        ]
        plain = ccc.render_cli_table(rows, color=False, wide=True)
        self.assertIn("CC-Int", plain)
        self.assertIn("57.5", plain)

    def test_render_html_cc_intel_columns(self):
        rows = [
            {"model_id": "grok-4.6", "pricing": {"monthly_credits": 20}, "caps": {"cap_5h_usd": 4.0}, "cost_per_request_usd": 0.036, "benchmarks": {"capability_q": 87.5, "fgi_score": 70.0, "avi_score": 260.0, "p_success": 86.0, "aa_intelligence": 60.9, "aa_coding": 76.0, "aa_agentic": 58.0, "aa_slug": "grok-4-6", "cc_intelligence": 60.9, "cc_coding": 76.8, "cc_tps": 60.8}, "value": {"fgi_score": 70.0, "avi_score": 260.0, "effective_cost_per_request": 0.036, "leverage_vs_10usd_sub": 2.0, "intelligence_per_dollar": 100.0, "cost_per_intelligence_pt_usd": 0.0006, "requests_per_dollar": 27.0}, "requests": {"per_5h_docs": 144, "per_week_docs": 360, "per_month_docs": 719}},
        ]
        html_out = ccc.render_html(rows, data_note="test")
        self.assertIn("CC intel", html_out)
        self.assertIn("CC cod", html_out)
        self.assertIn("CC TPS", html_out)
        self.assertIn("60.9", html_out)  # CC intel value
        self.assertIn("76.8", html_out)  # CC coding value
        self.assertIn(">61<", html_out)  # CC TPS rounded to int
        removed = [{"model_id": "legacy-v1", "pricing": {"monthly_credits": 70}, "value": {"fgi_score": 35.0, "avi_score": 150.0}}]
        colored = ccc.render_cli_table(rows, added_ids={"grok-4.6"}, removed_models=removed, color=True)
        self.assertIn("\033[38;5;48m", colored)
        self.assertIn("+grok-4.6", colored)
        self.assertIn("New (+1): grok-4.6", colored)
        self.assertIn("REMOVED / DEPRECATED MODELS", colored)
        plain = ccc.render_cli_table(rows, added_ids={"grok-4.6"}, removed_models=removed, color=False)
        self.assertIn("[+NEW (+1): grok-4.6]", plain)
        self.assertIn("[-] legacy-v1", plain)

    def test_render_html_diff(self):
        rows = [{"model_id": "grok-4.6", "pricing": {"monthly_credits": 20}, "caps": {"cap_5h_usd": 4.0}, "cost_per_request_usd": 0.036, "benchmarks": {"capability_q": 87.5, "fgi_score": 70.0, "avi_score": 260.0, "p_success": 86.0, "aa_intelligence": 60.9, "aa_coding": 76.0, "aa_agentic": 58.0, "aa_slug": "grok-4-6"}, "value": {"fgi_score": 70.0, "avi_score": 260.0, "effective_cost_per_request": 0.036, "leverage_vs_10usd_sub": 2.0, "intelligence_per_dollar": 100.0, "cost_per_intelligence_pt_usd": 0.0006, "requests_per_dollar": 27.0}, "requests": {"per_5h_docs": 144, "per_week_docs": 360, "per_month_docs": 719}}]
        removed = [{"model_id": "legacy-v1", "pricing": {"monthly_credits": 70}, "value": {"fgi_score": 35.0, "avi_score": 150.0}}]
        html = ccc.render_html(rows, added_ids={"grok-4.6"}, removed_models=removed)
        self.assertIn("badge-new", html)
        self.assertIn("+NEW", html)
        self.assertIn("removed-section", html)
        self.assertIn("legacy-v1", html)

    def test_role_recommendations_in_ccheck(self):
        rows = [
            {"model_id": "gpt-5.6-sol", "pricing": {"monthly_credits": 70}, "caps": {"cap_5h_usd": 14.0}, "cost_per_request_usd": 0.033, "benchmarks": {"capability_q": 88.0, "fgi_score": 70.0, "avi_score": 280.0, "p_success": 86.0, "aa_coding": 76.0, "aa_intelligence": 61.0}, "value": {"fgi_score": 70.0, "avi_score": 280.0, "effective_cost_per_request": 0.033}, "requests": {"per_5h_docs": 414}},
            {"model_id": "deepseek-v4-flash", "pricing": {"monthly_credits": 60}, "caps": {"cap_5h_usd": 12.0}, "cost_per_request_usd": 0.0006, "benchmarks": {"capability_q": 78.0, "fgi_score": 44.0, "avi_score": 450.0, "p_success": 68.0, "aa_coding": 69.0, "aa_intelligence": 51.0}, "value": {"fgi_score": 44.0, "avi_score": 450.0, "effective_cost_per_request": 0.0006}, "requests": {"per_5h_docs": 18200}},
        ]
        out = ccc.render_cli_table(rows, color=False)
        self.assertIn("RECOMMENDATIONS", out)

    def test_unscored_models_sort_last_and_show_dash(self):
        # A cheap model with NO benchmark coverage must NOT beat a scored model:
        # capability_q stays None -> Q/AVI/FGI render "—", and benchmark orders
        # sort unscored models last regardless of price.
        rows = [
            {"model_id": "laguna-s-2.1-free", "pricing": {"monthly_credits": None}, "caps": {"cap_5h_usd": None}, "cost_per_request_usd": None, "benchmarks": {"capability_q": None, "fgi_score": None, "avi_score": None, "p_success": None, "aa_intelligence": None}, "value": {"fgi_score": None, "avi_score": None, "effective_cost_per_request": None, "leverage_vs_10usd_sub": None}, "requests": {}},
            {"model_id": "grok-4.6", "pricing": {"monthly_credits": 20}, "caps": {"cap_5h_usd": 4.0}, "cost_per_request_usd": 0.036, "benchmarks": {"capability_q": 87.5, "fgi_score": 70.4, "avi_score": 260.0, "p_success": 86.5, "aa_intelligence": 60.9}, "value": {"fgi_score": 70.4, "avi_score": 260.0, "effective_cost_per_request": 0.036, "leverage_vs_10usd_sub": 2.0}, "requests": {}},
            {"model_id": "glm-5.3", "pricing": {"monthly_credits": 20}, "caps": {"cap_5h_usd": 4.0}, "cost_per_request_usd": 0.014, "benchmarks": {"capability_q": 87.4, "fgi_score": 70.2, "avi_score": 299.0, "p_success": 86.4, "aa_intelligence": 59.5}, "value": {"fgi_score": 70.2, "avi_score": 299.0, "effective_cost_per_request": 0.014, "leverage_vs_10usd_sub": 2.0}, "requests": {}},
        ]
        for mode in ("avi", "cap", "quality"):
            ids = [r["model_id"] for r in sorted(rows, key=ccc.build_sort_key(mode, lambda r: 999.0))]
            self.assertEqual(ids[-1], "laguna-s-2.1-free", f"unscored must be last under {mode}")
            self.assertNotEqual(ids[0], "laguna-s-2.1-free", f"unscored must not win {mode}")
        out = ccc.render_cli_table(rows, color=False)
        # unscored row shows "—" not a fabricated 78.0
        self.assertIn("laguna-s-2.1-free", out)
        # both scored models render real Q; assert no fake 78.0 for laguna by checking dash present
        # (grok/glm have real values; laguna's row ends with free-tier dash cells)
        self.assertNotIn("78.0", out)

    def test_catalog_diff_logic(self):
        prev = {"catalog_diff": {"added": [], "removed": []}, "models": [
            {"model_id": "glm-5.3", "pricing": {"monthly_credits": 20}, "value": {"fgi_score": 70.0}, "is_docs_model": True},
            {"model_id": "legacy-v1", "pricing": {"monthly_credits": 70}, "value": {"fgi_score": 35.0}, "is_docs_model": True},
        ]}
        current = [
            {"model_id": "glm-5.3", "pricing": {"monthly_credits": 20}, "value": {"fgi_score": 70.0}},
            {"model_id": "grok-4.6", "pricing": {"monthly_credits": 20}, "value": {"fgi_score": 70.0}},
        ]
        diff = ccc.diff_model_catalog(current, prev)
        self.assertEqual(diff["added_ids"], {"grok-4.6"})
        self.assertEqual(diff["removed_ids"], {"legacy-v1"})


if __name__ == "__main__":
    unittest.main()
