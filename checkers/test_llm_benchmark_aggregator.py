#!/usr/bin/env python3
import io
import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
import time
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
            self.assertIn(v["pool"], ["ocgo", "agy", "claude", "frontier", "api", "cline"])
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
        table = bc.render_cli_table(models, top_n=None)
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
        self.assertIn("LiveBench (%)", md)
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
        # Category averages are computed by the parser itself; read the parsed row
        # directly — find_livebench links tier-suffixed keys via the tier-stripped
        # base name (effort tiers are the only listing for many flagships).
        opus = parsed["claude-opus-5-xhigh-effort"]
        self.assertAlmostEqual(opus["coding"], 83.75)
        self.assertAlmostEqual(opus["reasoning"], 83.5)
        self.assertAlmostEqual(opus["overall"], 83.62)
        self.assertEqual(bc.find_livebench("claude-opus-5", parsed)["overall"], 83.62)
        flash = parsed["gemini-3.7-flash-high"]
        self.assertAlmostEqual(flash["coding"], 79.0)
        self.assertEqual(bc.find_livebench("gemini-3.7-flash", parsed)["overall"], 79.88)

    def test_version_safe_matching(self):
        # Variant fallback (P1 1.4 / S2-C2): exact-normalized keys match; a longer
        # key whose surplus carries digit tokens never matches (versions are
        # load-bearing). Tier/effort suffixes link via the tier-stripped base
        # name (best overall per base) — LiveBench lists flagships only there.
        live_mock = {
            "gemini-2-5-flash": {"model": "gemini-2.5-flash", "overall": 46.89},
            "gemini-3-7-flash": {"model": "gemini-3.7-flash", "overall": 79.90},
            "gemini-3-1-pro-preview": {"model": "gemini-3.1-pro-preview", "overall": 77.99},
        }
        rec37 = bc.find_livebench({"lm_slug": "gemini-3.7-flash", "display": "Gemini 3.7 Flash (Thinking)"}, live_mock)
        self.assertIsNotNone(rec37)  # exact-family match retained
        self.assertEqual(rec37["overall"], 79.90)
        rec31 = bc.find_livebench({"lm_slug": "gemini-3.1-pro", "display": "Gemini 3.1 Pro (High)"}, live_mock)
        self.assertIsNotNone(rec31)  # -preview surplus = tier token -> tier-base link
        self.assertEqual(rec31["overall"], 77.99)
        self.assertIsNone(bc.find_livebench({"lm_slug": "gemini-3.7-pro", "display": "Gemini 3.7 Pro"}, live_mock))  # version divergence
        suffixed_only = {"claude-opus-5-max": {"model": "claude-opus-5-max", "overall": 80.5}}
        rec_opus = bc.find_livebench("claude-opus-5", suffixed_only)
        self.assertIsNotNone(rec_opus)  # -max tier suffix -> tier-base link
        self.assertEqual(rec_opus["overall"], 80.5)
        # Best-per-base: multiple effort tiers collapse to the highest overall.
        tiered = {
            "claude-sonnet-4-6-thinking-auto-medium-effort": {"model": "cs46-m", "overall": 73.41},
            "claude-sonnet-4-6-thinking-auto-high-effort": {"model": "cs46-h", "overall": 75.59},
        }
        rec_s46 = bc.find_livebench({"lm_slug": "claude-sonnet-4-6"}, tiered)
        self.assertEqual(rec_s46["overall"], 75.59)
        # Model-variant tokens are NOT tiers: 'mimo-v2-pro' must never link to mimo-v2.5.
        self.assertIsNone(bc.find_livebench({"lm_slug": "mimo-v2.5"}, {"mimo-v2-pro": {"model": "mimo-v2-pro", "overall": 58.35}}))

    def test_lmarena_parsing_and_matching(self):
        html_sample = """
        <table>
            <tr><th>Rank</th><th>Model</th><th>Name</th><th>Score</th><th>Votes</th><th>Price</th><th>Context</th></tr>
            <tr>
                <td>9</td><td>icon</td><td title="gemini-3.7-flash-high">Gemini 3.7 Flash</td><td>1490.0±5</td><td>5,718</td><td>$0.38 / $1.88</td><td>1M</td>
            </tr>
            <tr>
                <td>10</td><td>icon</td><td title="gemini-3.7-flash">Gemini 3.7 Flash</td><td>1480.0±6</td><td>5,100</td><td>$0.38 / $1.88</td><td>1M</td>
            </tr>
        </table>
        """
        lm_map = bc.parse_lmarena(html_sample)
        self.assertIn("gemini-3.7-flash-high", lm_map)
        self.assertEqual(lm_map["gemini-3.7-flash-high"]["elo"], 1490.0)
        self.assertEqual(lm_map["gemini-3.7-flash-high"]["rank"], 9)

        # P1 1.4 / S1-C2: bare query must link only to the identically-normalized
        # row — never borrow an effort variant's ELO via substring containment.
        rec = bc.find_lmarena({"lm_slug": "gemini-3.7-flash", "display": "Gemini 3.7 Flash (Thinking)"}, lm_map)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["elo"], 1480.0)
        self.assertIsNone(bc.find_lmarena({"lm_slug": "gemini-3.7-flash"}, {"gemini-3.7-flash-high": {"elo": 1490.0}}))

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
        self.assertIn("GPT-5.6 Sol (Reasoning)", pareto_ids)
        self.assertIn("GPT-OSS 120B (Medium)", pareto_ids)
        self.assertIn("Gemini 3.7 Flash (Thinking)", pareto_ids)
        self.assertIn("Muse Spark 1.2 (Contributor)", pareto_ids)

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
        self.assertIn("RECOMMENDATIONS", table)
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


class TestBcheckCache(unittest.TestCase):

    def test_newest_snapshot_age_and_staleness(self):
        # S2-M2: age keys on the _YYYYMMDD date embedded in the filename — a
        # fresh clone/checkout gives every snapshot today's mtime, and must not
        # silence the only staleness defense in the offline design.
        with tempfile.TemporaryDirectory() as td:
            real_raw, real_data = bc.RAW, bc.DATA
            try:
                bc.RAW = bc.DATA = Path(td)
                self.assertIsNone(bc.newest_snapshot_age_h("*lmarena*20*.html"))
                snap = Path(td) / "lmarena_20260101.html"
                snap.write_text("x")  # mtime == now, exactly like a fresh clone
                self.assertGreater(bc.newest_snapshot_age_h("*lmarena*20*.html"), 30 * 24.0)
                note = bc.cache_staleness_note()
                self.assertIn("LMArena", note)
                self.assertIn("--fetch", note)
                # date-less filenames still fall back to mtime (checked by the
                # bc.snapshot_age_hours unit test; here just ensure no crash)
                (Path(td) / "livebench_20260101.csv").write_text("x")
                (Path(td) / "artificial_analysis_20260101.html").write_text("x")
                # newest matching snapshot wins: today-dated copies clear the note
                today = datetime.now(timezone.utc).strftime("%Y%m%d")
                for nm in (f"lmarena_{today}.html",
                           f"livebench_{today}.csv", f"artificial_analysis_{today}.html"):
                    (Path(td) / nm).write_text("x")
                self.assertEqual(bc.cache_staleness_note(), "")
            finally:
                bc.RAW, bc.DATA = real_raw, real_data

    def test_baseline_roundtrip_green_window(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "benchmarks.json"
            t0 = datetime(2026, 8, 28, tzinfo=timezone.utc)
            rows = [
                {"display": "Old Model", "base_metrics": {}},
                {"display": "New Model", "base_metrics": {}, "created_date": "2026-08-27T00:00:00Z"},
            ]
            diff = bc.diff_model_catalog(rows, None, id_key="display", now=t0)
            self.assertIn("New Model", diff["added_ids"])
            self.assertNotIn("Old Model", diff["added_ids"])
            p = bc.save_baseline(rows, diff, path=base)
            payload = json.loads(p.read_text(encoding="utf-8"))
            self.assertIn("catalog_diff", payload)
            self.assertIn("New Model", payload["catalog_diff"]["added"])
            prev = bc.load_previous_snapshot(base)
            rows2 = [{"display": "Old Model", "base_metrics": {}}, {"display": "New Model", "base_metrics": {}}]
            d3 = bc.diff_model_catalog(rows2, prev, id_key="display", now=t0 + timedelta(days=3))
            self.assertIn("New Model", d3["added_ids"])  # first_seen inherited -> still green
            self.assertEqual(d3["removed_ids"], set())
            d8 = bc.diff_model_catalog(rows2, prev, id_key="display", now=t0 + timedelta(days=8))
            self.assertNotIn("New Model", d8["added_ids"])  # aged past 7d window

    def test_aa_quality_influences_capability_q(self):
        import copy
        cat = copy.deepcopy(bc.MODELS_CATALOG)
        bc.calculate_composite_scores(cat)
        k = next(iter(cat))
        base_q = cat[k]["capability_q"]
        cat[k]["base_metrics"]["aa_quality"] = (cat[k]["base_metrics"].get("aa_quality") or 0.0) + 50.0
        bc.calculate_composite_scores(cat)
        self.assertGreater(cat[k]["capability_q"], base_q)

    def test_stale_note_renders_cli_and_html(self):
        bc.calculate_composite_scores(bc.MODELS_CATALOG)
        models = list(bc.MODELS_CATALOG.values())
        tui = bc.render_cli_table(models, color=False, stale_note="cached responses >24h — run with --fetch: LMArena missing")
        self.assertIn("cached responses >24h", tui)
        self.assertIn("[!]", tui)
        h = bc.render_html_report(models, stale_note="stale: LMArena missing")
        self.assertIn("stale: LMArena missing", h)



class TestFetchPath(unittest.TestCase):
    """P1 1.5 (S2-C1): fetch=True must parse live payloads and write dated snapshots.

    The uncommitted refactor left `if do_fetch:` NameErrors swallowed by bare
    excepts; these tests route a monkeypatched fetch_url (precedent:
    test_newest_snapshot_age_and_staleness) and fail if any source silently
    discards its payload again.
    """

    CSV = "model,code_generation,math\nprobe-model-9,81.5,70.5\n"
    CATS = json.dumps({"Coding": ["code_generation"], "Mathematics": ["math"]})
    LM_HTML = (
        "<table><tr><th>Rank</th><th>Model</th><th>Name</th><th>Score</th>"
        "<th>Votes</th><th>Price</th><th>Context</th></tr>"
        '<tr><td>1</td><td>i</td><td title="probe-model-9">Probe</td>'
        "<td>1500.0±1</td><td>10</td><td>$1 / $2</td><td>1M</td></tr></table>"
    )
    AA_HTML = (
        'preamble\nself.__next_f.push([1,"'
        + '"models":'
        + json.dumps([{"slug": "probe-model-9", "name": "P9", "intelligenceIndex": 55.0, "codingIndex": 50.0}])
        + '"])'
    )

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._real_raw, self._real_root = bc.RAW, bc.ROOT
        bc.RAW = bc.ROOT = Path(self._tmp.name)
        self.stamp = datetime.now().strftime("%Y%m%d")

    def tearDown(self):
        bc.RAW, bc.ROOT = self._real_raw, self._real_root
        self._tmp.cleanup()

    def test_livebench_fetch_true_parses_and_saves(self):
        with unittest.mock.patch.object(
            bc, "fetch_url",
            side_effect=lambda url, timeout=15: self.CSV if "livebench" in url and "categor" not in url else self.CATS,
        ):
            out = bc.load_livebench_data(fetch=True)
        self.assertIn("probe-model-9", out)
        self.assertEqual(out["probe-model-9"]["overall"], 76.0)
        snap = Path(self._tmp.name) / f"livebench_{self.stamp}.csv"
        self.assertTrue(snap.exists())
        self.assertEqual(snap.read_text(encoding="utf-8"), self.CSV)
        self.assertTrue((Path(self._tmp.name) / f"livebench_categories_{self.stamp}.json").exists())

    def test_lmarena_fetch_true_parses_and_saves(self):
        with unittest.mock.patch.object(bc, "fetch_url", return_value=self.LM_HTML):
            out = bc.load_lmarena_data(fetch=True)
        self.assertIn("probe-model-9", out)
        self.assertEqual(out["probe-model-9"]["elo"], 1500.0)
        snap = Path(self._tmp.name) / f"lmarena_{self.stamp}.html"
        self.assertTrue(snap.exists())
        self.assertEqual(snap.read_text(encoding="utf-8"), self.LM_HTML)

    def test_aa_fetch_true_parses_and_saves(self):
        with unittest.mock.patch.object(bc, "fetch_url", return_value=self.AA_HTML):
            out = bc.load_aa_data(fetch=True)
        self.assertIn("probe-model-9", out)
        self.assertEqual(out["probe-model-9"]["intelligenceIndex"], 55.0)
        snap = Path(self._tmp.name) / f"artificial_analysis_{self.stamp}.html"
        self.assertTrue(snap.exists())

    def test_fetch_exception_is_logged_not_swallowed(self):
        with unittest.mock.patch.object(bc, "fetch_url", side_effect=OSError("simulated outage")):
            with unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                out = bc.load_lmarena_data(fetch=True)
        self.assertEqual(out, {})
        self.assertIn("LMArena", err.getvalue())
        self.assertIn("simulated outage", err.getvalue())


class TestUniversalAggregatorAndDisplay(unittest.TestCase):
    def test_format_model_display_name(self):
        disp, prov = bc.format_model_display_name("glm-5.3-flash")
        self.assertEqual(disp, "GLM-5.3 Flash")
        self.assertEqual(prov, "Zhipu AI")

        disp, prov = bc.format_model_display_name("deepseek-v4-flash-vision-exp")
        self.assertEqual(disp, "DeepSeek V4 Flash Vision Exp")
        self.assertEqual(prov, "DeepSeek")

        disp, prov = bc.format_model_display_name("qwen3.8-flash")
        self.assertEqual(disp, "Qwen3.8 Flash")
        self.assertEqual(prov, "Alibaba")

        disp, prov = bc.format_model_display_name("hy4-preview")
        self.assertEqual(disp, "Hunyuan 4 Preview")
        self.assertEqual(prov, "Tencent")

        disp, prov = bc.format_model_display_name("minimax-m3")
        self.assertEqual(disp, "MiniMax M3")
        self.assertEqual(prov, "MiniMax")

    def test_build_universal_catalog_includes_upstream_models(self):
        live_map = bc.load_livebench_data(fetch=False)
        lm_map = bc.load_lmarena_data(fetch=False)
        aa_map = bc.load_aa_data(fetch=False)
        catalog = bc.build_universal_catalog(live_map=live_map, lm_map=lm_map, aa_map=aa_map)
        self.assertGreater(len(catalog), 500)
        self.assertTrue(any(m.get("display") == "Hunyuan 4 Preview" for m in catalog.values()))
        m = next(m for m in catalog.values() if m.get("display") == "Hunyuan 4 Preview")
        self.assertEqual(m["provider"], "Tencent")
        self.assertEqual(m["pool"], "api")

    def test_cli_table_top_n_and_all(self):
        live_map = bc.load_livebench_data(fetch=False)
        lm_map = bc.load_lmarena_data(fetch=False)
        aa_map = bc.load_aa_data(fetch=False)
        catalog = bc.build_universal_catalog(live_map=live_map, lm_map=lm_map, aa_map=aa_map)
        bc.calculate_composite_scores(catalog)
        models = [m for m in catalog.values() if m.get("livebench") or m.get("aa_live_quality") or m.get("base_metrics", {}).get("lm_elo") or m.get("base_metrics", {}).get("aa_quality")]
        models.sort(key=lambda m: m.get("composite_score", 0), reverse=True)

        # Default top_n=30
        table_30 = bc.render_cli_table(models, top_n=30, color=False)
        self.assertIn("(Top 30 shown)", table_30)
        self.assertIn("🥇#1", table_30)
        self.assertIn(" #30", table_30)
        self.assertNotIn(" #31", table_30)

        # Top_n=5
        table_5 = bc.render_cli_table(models, top_n=5, color=False)
        self.assertIn("(Top 5 shown)", table_5)
        self.assertIn(" #5", table_5)
        self.assertNotIn(" #6", table_5)

        # Full catalog top_n=None
        table_all = bc.render_cli_table(models, top_n=None, color=False)
        self.assertNotIn("Top 30 shown", table_all)

    def test_markdown_and_html_top_n(self):
        live_map = bc.load_livebench_data(fetch=False)
        lm_map = bc.load_lmarena_data(fetch=False)
        aa_map = bc.load_aa_data(fetch=False)
        catalog = bc.build_universal_catalog(live_map=live_map, lm_map=lm_map, aa_map=aa_map)
        bc.calculate_composite_scores(catalog)
        models = [m for m in catalog.values() if m.get("livebench") or m.get("aa_live_quality") or m.get("base_metrics", {}).get("lm_elo") or m.get("base_metrics", {}).get("aa_quality")]
        models.sort(key=lambda m: m.get("composite_score", 0), reverse=True)

        md = bc.render_markdown_report(models, top_n=30)
        self.assertIn("Showing top 30 of", md)

        html_top30 = bc.render_html_report(models, top_n=30)
        self.assertIn("Master Leaderboard", html_top30)

    def test_partition_models_by_benchmark_coverage(self):
        live_map = bc.load_livebench_data(fetch=False)
        lm_map = bc.load_lmarena_data(fetch=False)
        aa_map = bc.load_aa_data(fetch=False)
        catalog = bc.build_universal_catalog(live_map=live_map, lm_map=lm_map, aa_map=aa_map)
        bc.calculate_composite_scores(catalog)
        models = [m for m in catalog.values() if m.get("livebench") or m.get("aa_live_quality") or m.get("base_metrics", {}).get("lm_elo") or m.get("base_metrics", {}).get("aa_quality")]

        parts = bc.partition_models_by_benchmark_coverage(models)
        self.assertGreater(len(parts["tri_verified"]), 20)
        self.assertGreater(len(parts["missing_livebench"]), 10)
        self.assertGreater(len(parts["missing_lmarena"]), 5)
        self.assertGreater(len(parts["single_source"]), 100)

        # Every model in tri_verified has all 3 signals
        for m in parts["tri_verified"]:
            self.assertIsNotNone(m.get("livebench"))
            self.assertIsNotNone(m.get("base_metrics", {}).get("lm_elo"))
            self.assertTrue(m.get("aa_live_quality") is not None or m.get("base_metrics", {}).get("aa_quality") is not None)

    def test_sub_tables_cli_md_html_rendering(self):
        sample_sub = [
            {
                "display": "Sample Partial Model",
                "pool": "api",
                "tier": "Benchmark Model",
                "capability_q": 85.0,
                "p_success": 82.0,
                "effective_cost": 2.50,
                "price_in": 1.0,
                "price_out": 3.0,
                "base_metrics": {"lm_elo": 1450},
                "aa_live_quality": 45.0,
            }
        ]
        cli_sub = bc.render_sub_table_cli(sample_sub, "Test Sub Table", color=False, top_n=10)
        self.assertIn("Test Sub Table", cli_sub)
        self.assertIn("Sample Partial Model", cli_sub)
        self.assertIn("1450", cli_sub)

        md_sub = bc.render_sub_table_md(sample_sub, "Test Markdown Sub", top_n=10)
        self.assertIn("Test Markdown Sub", md_sub)
        self.assertIn("Sample Partial Model", md_sub)

        html_sub = bc.render_sub_table_html(sample_sub, "Test HTML Sub", top_n=10)
        self.assertIn("Test HTML Sub", html_sub)
        self.assertIn("Sample Partial Model", html_sub)


if __name__ == "__main__":
    unittest.main()
