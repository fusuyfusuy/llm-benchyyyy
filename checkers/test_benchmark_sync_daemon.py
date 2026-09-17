#!/usr/bin/env python3
"""
test_benchmark_sync_daemon.py — Unit tests for 08:00 daily sync daemon and cache engine
"""
import datetime as dt
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import benchmark_sync_daemon as bsd
import llm_benchmark_aggregator as lba


class TestBenchmarkSyncDaemon(unittest.TestCase):
    def test_seconds_until_next_target_time(self):
        sec = bsd.seconds_until_next_target_time(8, 0)
        self.assertIsInstance(sec, float)
        self.assertGreater(sec, 0)
        self.assertLessEqual(sec, 86400)

        # Explicit mock time: at 07:00, 1 hour (3600s) until 08:00
        mock_now = dt.datetime(2026, 9, 1, 7, 0, 0)
        with patch("datetime.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *args, **kw: dt.datetime(*args, **kw)
            sec_7am = bsd.seconds_until_next_target_time(8, 0)
            self.assertEqual(sec_7am, 3600.0)

        # Explicit mock time: at 09:00, 23 hours (82800s) until next day 08:00
        mock_now_9am = dt.datetime(2026, 9, 1, 9, 0, 0)
        with patch("datetime.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now_9am
            mock_dt.side_effect = lambda *args, **kw: dt.datetime(*args, **kw)
            sec_9am = bsd.seconds_until_next_target_time(8, 0)
            self.assertEqual(sec_9am, 82800.0)

    def test_get_cache_status(self):
        st = bsd.get_cache_status()
        self.assertIn("status_report", st)
        self.assertIn("next_sync", st)
        self.assertIn("hours_until_next", st)

        feed_names = {r["feed"] for r in st["status_report"]}
        self.assertIn("LiveBench CSV", feed_names)
        self.assertIn("LMArena HTML", feed_names)
        self.assertIn("Artificial Analysis HTML", feed_names)
        self.assertIn("OpenRouter Models", feed_names)
        self.assertIn("CommandCode GOAT Docs", feed_names)
        self.assertIn("Cline Models", feed_names)

    def test_sync_all_sources_mocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_raw = pathlib.Path(tmpdir) / "raw"
            tmp_data = pathlib.Path(tmpdir)
            fake_cat = {
                f"m{i}": {"display": f"Model {i}", "pool": "api",
                          "livebench": {"overall": 80.0 + i},
                          "base_metrics": {}}
                for i in range(3)
            }
            with patch.object(bsd, "RAW", tmp_raw), patch.object(bsd, "DATA", tmp_data), patch.object(lba, "DATA", tmp_data):
                with patch.object(bsd, "fetch_url_content", return_value=("x" * 600_000)):
                    with patch("llm_benchmark_aggregator.load_livebench_data", return_value={}):
                        with patch("llm_benchmark_aggregator.load_lmarena_data", return_value={}):
                            with patch("llm_benchmark_aggregator.load_aa_data", return_value={}):
                                with patch("llm_benchmark_aggregator.build_universal_catalog", return_value=dict(fake_cat)):
                                    res = bsd.sync_all_sources(verbose=False, force=True)
                                    self.assertIn("livebench_csv", res)
                                    self.assertIn("lmarena", res)
                                    self.assertIn("artificial_analysis", res)
                                    self.assertIn("openrouter", res)
                                    self.assertIn("commandcode_goat", res)
                                    self.assertIn("cline_models", res)
                                    self.assertTrue((tmp_data / "benchmarks.json").exists())

    def test_fetch_failure_keeps_cache(self):
        # Failure bodies must never overwrite good cache; 0-model runs must not touch the baseline.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_raw = pathlib.Path(tmpdir) / "raw"
            tmp_raw.mkdir()
            tmp_data = pathlib.Path(tmpdir)
            today = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
            good = "GOOD" * 30_000
            p = tmp_raw / f"lmarena_{today}.html"
            p.write_text(good)
            with patch.object(bsd, "RAW", tmp_raw), patch.object(bsd, "DATA", tmp_data), patch.object(lba, "DATA", tmp_data):
                with patch.object(bsd, "fetch_url_content", return_value="oops"):
                    with patch("llm_benchmark_aggregator.load_livebench_data", return_value={}):
                        with patch("llm_benchmark_aggregator.load_lmarena_data", return_value={}):
                            with patch("llm_benchmark_aggregator.load_aa_data", return_value={}):
                                res = bsd.sync_all_sources(verbose=False, force=True)
            self.assertEqual(p.read_text(), good)
            self.assertEqual(res["lmarena"], p)
            self.assertIsNone(res["livebench_csv"])
            self.assertNotIn("baseline_json", res)
            self.assertFalse((tmp_data / "benchmarks.json").exists())

    def test_collapsed_baseline_refused(self):
        # 3 evaluated vs 200 prev (<50%) must keep benchmarks.json byte-identical.
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_raw = pathlib.Path(tmpdir) / "raw"
            tmp_raw.mkdir()
            tmp_data = pathlib.Path(tmpdir)
            prev_models = [{"display": f"Prev {i}", "pool": "api"} for i in range(200)]
            prev = {"generated_at": "2026-09-01T00:00:00+00:00",
                    "catalog_diff": {"added": [], "removed": [], "total_current": 200},
                    "models": prev_models}
            (tmp_data / "benchmarks.json").write_text(json.dumps(prev))
            small_cat = {
                f"m{i}": {"display": f"Model {i}", "pool": "api",
                          "livebench": {"overall": 80.0 + i},
                          "base_metrics": {}}
                for i in range(3)
            }
            with patch.object(bsd, "RAW", tmp_raw), patch.object(bsd, "DATA", tmp_data), patch.object(lba, "DATA", tmp_data):
                with patch.object(bsd, "fetch_url_content", return_value=("x" * 600_000)):
                    with patch("llm_benchmark_aggregator.load_livebench_data", return_value={}):
                        with patch("llm_benchmark_aggregator.load_lmarena_data", return_value={}):
                            with patch("llm_benchmark_aggregator.load_aa_data", return_value={}):
                                with patch("llm_benchmark_aggregator.build_universal_catalog", return_value=dict(small_cat)):
                                    res = bsd.sync_all_sources(verbose=False, force=True)
            self.assertNotIn("baseline_json", res)
            kept = json.loads((tmp_data / "benchmarks.json").read_text())
            self.assertEqual(len(kept["models"]), 200)

    def test_fetch_rejects_tiny_error_body(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"404 Not Found"
        with patch("urllib.request.urlopen", return_value=response), patch.object(bsd, "log"):
            self.assertIsNone(bsd.fetch_url_content("https://example.test/feed", max_retries=1))

    def test_sync_lock_rejects_concurrent_process(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = pathlib.Path(tmpdir) / "sync.lock"
            with patch.object(bsd, "LOCK_PATH", lock_path), patch("fcntl.flock", side_effect=BlockingIOError):
                with self.assertRaisesRegex(RuntimeError, "already running"):
                    with bsd.sync_lock():
                        pass

    def test_status_ignores_livebench_cost_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = pathlib.Path(tmpdir)
            raw = data / "raw"
            raw.mkdir()
            (raw / "livebench_20260101.csv").write_text("valid")
            (raw / "livebench_cost_20990101.csv").write_text("wrong")
            with patch.object(bsd, "RAW", raw), patch.object(bsd, "DATA", data):
                status = bsd.get_cache_status()
            livebench = next(row for row in status["status_report"] if row["feed"] == "LiveBench CSV")
            self.assertEqual(livebench["latest_file"], "livebench_20260101.csv")

    def test_install_cron_output(self):
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            bsd.install_cron()
            output = out.getvalue()
            self.assertIn("0 8 * * *", output)
            self.assertIn("benchmark_sync_daemon.py", output)
            self.assertIn("--sync-now", output)

    def test_install_systemd_files(self):
        with tempfile.TemporaryDirectory() as tmp_home:
            p_home = pathlib.Path(tmp_home)
            with patch("pathlib.Path.home", return_value=p_home):
                with patch("sys.stdout", new_callable=io.StringIO):
                    bsd.install_systemd()
                    svc = p_home / ".config" / "systemd" / "user" / "llm-bench-sync.service"
                    tmr = p_home / ".config" / "systemd" / "user" / "llm-bench-sync.timer"
                    self.assertTrue(svc.exists())
                    self.assertTrue(tmr.exists())
                    self.assertIn("OnCalendar=*-*-* 08:00:00", tmr.read_text())
                    self.assertIn("--sync-now", svc.read_text())

    def test_get_cache_status_includes_opencode_and_akatsuki(self):
        st = bsd.get_cache_status()
        self.assertIn("akatsuki_status", st)
        feed_names = {r["feed"] for r in st["status_report"]}
        self.assertIn("OpenCode Go Docs", feed_names)
        self.assertIn("OpenCode Go Models", feed_names)
        self.assertIn("OpenCode Zen Models", feed_names)
        self.assertIn("OpenCode Go Live", feed_names)
        self.assertIn("CommandCode Live", feed_names)
        self.assertIn("Free Models", feed_names)
        self.assertIn("Stealth Models", feed_names)

    def test_generate_akatsuki_radar_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_data = pathlib.Path(tmpdir)
            bench = {"models": [
                {"display": "Test-Opus", "pool": "api", "livebench": {"overall": 89.5}, "aa_live_quality": 88.0, "base_metrics": {"lm_elo": 1400}}
            ]}
            (tmp_data / "benchmarks.json").write_text(json.dumps(bench))
            oc = {"models": [
                {"name": "test-oc-flash", "limit": 30, "req_mo": 50000, "q_cap": 85.0, "cost_per_req": 0.001, "value_score": 500.0}
            ]}
            (tmp_data / "ocgo_live.json").write_text(json.dumps(oc))
            cc = {"models": [
                {"name": "test-cc-goat", "credits": 60, "req_mo": 40000, "q_cap": 84.0, "cost_per_req": 0.0012, "value_score": 480.0}
            ]}
            (tmp_data / "cc_live.json").write_text(json.dumps(cc))
            free = {"models": [
                {"model_id": "test-free-m", "provider": "opencode", "q_cap": 80.0, "p_success": 0.75, "fgi": 50.0, "context_length": 128000}
            ]}
            (tmp_data / "free_models.json").write_text(json.dumps(free))

            with patch.object(bsd, "DATA", tmp_data):
                content = bsd.generate_akatsuki_radar_content("20260916")
                self.assertTrue(content.startswith("---"))
                self.assertIn('title: "Live Model Benchmarks & Pricing Radar"', content)
                self.assertIn("Test-Opus", content)
                self.assertIn("test-oc-flash", content)
                self.assertIn("test-cc-goat", content)
                self.assertIn("test-free-m", content)
                self.assertIn("[[30-Agents/Agents-MOC|Agents MOC]]", content)
                self.assertIn("[[20-Projects/llm-benchyyyy|llm-benchyyyy]]", content)

    def test_save_results_to_akatsuki(self):
        with tempfile.TemporaryDirectory() as tmp_vault:
            p_vault = pathlib.Path(tmp_vault)
            (p_vault / "30-Agents").mkdir()
            (p_vault / "20-Projects").mkdir()
            moc_file = p_vault / "30-Agents" / "Agents-MOC.md"
            moc_file.write_text("## 🔬 Model Benchmarking & Empirical Evaluations\n\n- [[30-Agents/Model-Benchmarks-2026|Model Benchmarks 2026]]\n")
            proj_file = p_vault / "20-Projects" / "llm-benchyyyy.md"
            proj_file.write_text("## 🔗 Related\n- [[INDEX|Master Index]]\n")

            with tempfile.TemporaryDirectory() as tmp_data:
                p_data = pathlib.Path(tmp_data)
                with patch.object(bsd, "DATA", p_data), patch.dict(os.environ, {"AKATSUKI_VAULT": str(p_vault)}), patch("shutil.which", return_value=None):
                    saved = bsd.save_results_to_akatsuki(verbose=False)
                    self.assertTrue(saved)
                    note_path = p_vault / "30-Agents" / "Model-Benchmarks-Live.md"
                    self.assertTrue(note_path.exists())
                    self.assertIn("[[30-Agents/Model-Benchmarks-Live|Live Model Benchmarks & Pricing Radar]]", moc_file.read_text())
                    self.assertIn("[[30-Agents/Model-Benchmarks-Live|Live Model Benchmarks & Pricing Radar]]", proj_file.read_text())

    def test_refresh_suite_results(self):
        results = {}
        with patch.object(bsd, "run_checker_script", return_value=True):
            status = bsd.refresh_suite_results(results, verbose=False)
            self.assertTrue(status["ocgo"])
            self.assertTrue(status["cc"])
            self.assertTrue(status["free"])
            self.assertTrue(status["stealth"])
            self.assertIn("ocgo_live_json", results)
            self.assertIn("cc_live_json", results)
            self.assertIn("free_models_json", results)
            self.assertIn("stealth_models_json", results)


if __name__ == "__main__":
    unittest.main()
