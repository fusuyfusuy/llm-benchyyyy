#!/usr/bin/env python3
import json
import unittest
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import llm_benchmark_aggregator as bc


class TestBenchmarksCheck(unittest.TestCase):
    def test_catalog_structure(self):
        self.assertGreater(len(bc.MODELS_CATALOG), 10)
        for k, v in bc.MODELS_CATALOG.items():
            self.assertIn("display", v)
            self.assertIn("pool", v)
            self.assertIn(v["pool"], ["ocgo", "agy", "claude", "frontier"])
            self.assertIn("base_metrics", v)
            self.assertIn("price_in", v)
            self.assertIn("price_out", v)

    def test_composite_scoring(self):
        bc.calculate_composite_scores(bc.MODELS_CATALOG)
        for k, v in bc.MODELS_CATALOG.items():
            self.assertIn("composite_score", v)
            self.assertIn("capability_q", v)
            self.assertIn("p_success", v)
            self.assertIn("token_multiplier", v)
            self.assertIn("effective_cost", v)
            self.assertIn("avi_score", v)
            self.assertIn("fgi_score", v)
            self.assertIn("bfi_score", v)
            self.assertGreater(v["composite_score"], 40.0)
            self.assertLessEqual(v["composite_score"], 100.0)
            self.assertGreater(v["p_success"], 0.0)
            self.assertLessEqual(v["p_success"], 100.0)
            self.assertGreater(v["token_multiplier"], 1.0)
            self.assertGreater(v["effective_cost"], 0.0)
            self.assertGreater(v["avi_score"], 0.0)

    def test_render_table(self):
        bc.calculate_composite_scores(bc.MODELS_CATALOG)
        models = list(bc.MODELS_CATALOG.values())
        table = bc.render_cli_table(models)
        self.assertIn("Claude Opus 5", table)
        self.assertIn("Claude Fable 5", table)
        self.assertIn("GPT-5.6 Sol", table)
        self.assertIn("GPT 5.5", table)
        self.assertIn("Gemini 3.1 Pro", table)
        self.assertIn("GLM-5.3", table)
        self.assertIn("Kimi K3", table)
        self.assertNotIn("o3 Pro", table)
        self.assertNotIn("o3-pro", table)
        self.assertNotIn("3.7 Sonnet", table)
        self.assertNotIn("DeepSeek R1", table)

    def test_render_markdown(self):
        bc.calculate_composite_scores(bc.MODELS_CATALOG)
        models = list(bc.MODELS_CATALOG.values())
        md = bc.render_markdown_report(models)
        self.assertIn("# Consolidated LLM Benchmark", md)
        self.assertIn("| Model |", md)
        self.assertIn("ARC-AGI-2", md)
        self.assertIn("AVI (Value)", md)

    def test_livebench_parsing(self):
        sample_csv = """model,code_generation,code_completion,theory_of_mind,zebra_puzzle
claude-opus-5-xhigh-effort,85.0,82.5,88.0,79.0
gemini-3.7-flash-high,80.0,78.0,84.0,77.5
"""
        sample_cats = """{
            "Coding": ["code_generation", "code_completion"],
            "Reasoning": ["theory_of_mind", "zebra_puzzle"]
        }"""
        parsed = bc.parse_livebench(sample_csv, sample_cats)
        self.assertEqual(len(parsed), 2)
        opus = bc.find_livebench("claude-opus-5", parsed)
        self.assertIsNotNone(opus)
        self.assertAlmostEqual(opus["coding"], 83.75)
        self.assertAlmostEqual(opus["reasoning"], 83.5)
        self.assertEqual(opus["overall"], 83.62)

        flash = bc.find_livebench("gemini-3.7-flash", parsed)
        self.assertIsNotNone(flash)
        self.assertAlmostEqual(flash["coding"], 79.0)

    def test_version_safe_matching(self):
        live_mock = {
            "gemini-2-5-flash-high": {"model": "gemini-2.5-flash-high", "overall": 46.89},
            "gemini-3-7-flash-high": {"model": "gemini-3.7-flash-high", "overall": 79.90},
            "gemini-3-1-pro-preview-high": {"model": "gemini-3.1-pro-preview-high", "overall": 77.99},
        }
        # Gemini 3.7 Flash should match 3.7, NOT 2.5
        rec37 = bc.find_livebench({"lm_slug": "gemini-3.7-flash", "display": "Gemini 3.7 Flash (Thinking)"}, live_mock)
        self.assertIsNotNone(rec37)
        self.assertEqual(rec37["overall"], 79.90)

        # Gemini 3.1 Pro should match 3.1, NOT 2.5
        rec31 = bc.find_livebench({"lm_slug": "gemini-3.1-pro", "display": "Gemini 3.1 Pro (High)"}, live_mock)
        self.assertIsNotNone(rec31)
        self.assertEqual(rec31["overall"], 77.99)

    def test_lmarena_parsing_and_matching(self):
        html_sample = """
        <table>
            <tr><th>Rank</th><th>Model</th><th>Name</th><th>Score</th><th>Votes</th><th>Price</th><th>Context</th></tr>
            <tr>
                <td>9</td><td>icon</td><td title="gemini-3.7-flash-high">Gemini 3.7 Flash</td><td>1490.0±5</td><td>5,718</td><td>$0.38 / $1.88</td><td>1M</td>
            </tr>
        </table>
        """
        lm_map = bc.parse_lmarena(html_sample)
        self.assertIn("gemini-3.7-flash-high", lm_map)
        self.assertEqual(lm_map["gemini-3.7-flash-high"]["elo"], 1490.0)
        self.assertEqual(lm_map["gemini-3.7-flash-high"]["rank"], 9)

        rec = bc.find_lmarena({"lm_slug": "gemini-3.7-flash", "display": "Gemini 3.7 Flash (Thinking)"}, lm_map)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["elo"], 1490.0)

    def test_aa_parsing_and_matching(self):
        # Mirrors the real AA page shape: no static __NEXT_DATA__ blob, data ships
        # as a "models":[...] array inside an RSC flight chunk.
        models_json = json.dumps([
            {
                "slug": "gemini-3-7-flash",
                "name": "Gemini 3.7 Flash",
                "intelligenceIndex": 89.0,
                "codingIndex": 91.0,
                "agenticIndex": 85.0,
                "medianOutputTokensPerSecond": 135.0,
                "price1mInputTokens": 0.38,
                "price1mOutputTokens": 1.88,
            }
        ])
        html_sample = (
            'irrelevant preamble noise\n'
            'self.__next_f.push([1,"' + '"models":' + models_json + '"])'
        )
        aa_map = bc.parse_aa(html_sample)
        self.assertIn("gemini-3-7-flash", aa_map)
        self.assertEqual(aa_map["gemini-3-7-flash"]["intelligenceIndex"], 89.0)
        self.assertEqual(aa_map["gemini-3-7-flash"]["medianTps"], 135.0)

        rec = bc.find_aa({"aa_slug": "gemini-3-7-flash", "lm_slug": "gemini-3.7-flash", "display": "Gemini 3.7 Flash (Thinking)"}, aa_map)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["codingIndex"], 91.0)

    def test_pareto_frontier_and_close_calls(self):
        bc.calculate_composite_scores(bc.MODELS_CATALOG)
        models = list(bc.MODELS_CATALOG.values())
        pareto_ids = bc.compute_pareto_frontier(models)
        self.assertIn("Claude Opus 5 (Thinking)", pareto_ids)
        self.assertIn("DeepSeek V4 Flash", pareto_ids)
        self.assertIn("GPT-OSS 120B (Medium)", pareto_ids)
        self.assertIn("Gemini 3.7 Flash (Thinking)", pareto_ids)
        self.assertIn("GPT 5.6 Luna", pareto_ids)

    def test_render_podium_table(self):
        bc.calculate_composite_scores(bc.MODELS_CATALOG)
        models = list(bc.MODELS_CATALOG.values())
        podium_plain = bc.render_podium_table(models, color=False)
        self.assertIn("COLUMN WINNERS & PODIUM LEADERS", podium_plain)
        self.assertIn("Q(Cap) — Capability", podium_plain)
        self.assertIn("AVI — Daily Driver ROI", podium_plain)
        self.assertIn("1st Place (Gold)", podium_plain)

    def test_role_recommendations_in_bcheck(self):
        bc.calculate_composite_scores(bc.MODELS_CATALOG)
        models = list(bc.MODELS_CATALOG.values())
        table = bc.render_cli_table(models, color=False)
        self.assertIn("ROLE RECOMMENDATIONS", table)
        self.assertIn("Architecture", table)
        self.assertIn("Daily Driver", table)

        html = bc.render_html_report(models)
        self.assertIn("Dynamic Function & Role Recommendations", html)

    def test_bcheck_catalog_diff(self):
        bc.calculate_composite_scores(bc.MODELS_CATALOG)
        models = list(bc.MODELS_CATALOG.values())
        added_id = "Claude Fable 5 (High)"
        removed_models = [
            {
                "display": "Legacy Model 1",
                "pool": "claude",
                "fgi_score": 40.0,
                "avi_score": 100.0,
            }
        ]

        # Colored CLI table
        tui_colored = bc.render_cli_table(
            models,
            color=True,
            added_ids={added_id},
            removed_models=removed_models,
        )
        self.assertIn("\033[38;5;48m", tui_colored)
        self.assertIn("+Claude Fable 5", tui_colored)
        self.assertIn(f"New (+1): {added_id}", tui_colored)
        self.assertIn("\033[38;5;196m", tui_colored)
        self.assertIn("REMOVED / DEPRECATED MODELS", tui_colored)
        self.assertIn("Legacy Model 1", tui_colored)

        # Plain CLI table
        tui_plain = bc.render_cli_table(
            models,
            color=False,
            added_ids={added_id},
            removed_models=removed_models,
        )
        self.assertIn("+Claude Fable 5", tui_plain)
        self.assertIn(f"[+NEW (+1): {added_id}]", tui_plain)
        self.assertIn("[-] Legacy Model 1", tui_plain)

        # HTML
        html_text = bc.render_html_report(
            models,
            added_ids={added_id},
            removed_models=removed_models,
        )
        self.assertIn("badge-new", html_text)
        self.assertIn("+NEW", html_text)
        self.assertIn("removed-section", html_text)
        self.assertIn("Legacy Model 1", html_text)


if __name__ == "__main__":
    unittest.main()
