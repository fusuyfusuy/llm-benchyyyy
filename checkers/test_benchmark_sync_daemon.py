#!/usr/bin/env python3
"""
test_benchmark_sync_daemon.py — Unit tests for 08:00 daily sync daemon and cache engine
"""
import datetime as dt
import io
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
            with patch.object(bsd, "RAW", tmp_raw), patch.object(bsd, "DATA", tmp_data), patch.object(lba, "DATA", tmp_data):
                with patch.object(bsd, "fetch_url_content", return_value="<mock content>"):
                    with patch("llm_benchmark_aggregator.load_livebench_data", return_value={}):
                        with patch("llm_benchmark_aggregator.load_lmarena_data", return_value={}):
                            with patch("llm_benchmark_aggregator.load_aa_data", return_value={}):
                                res = bsd.sync_all_sources(verbose=False, force=True)
                                self.assertIn("livebench_csv", res)
                                self.assertIn("lmarena", res)
                                self.assertIn("artificial_analysis", res)
                                self.assertIn("openrouter", res)
                                self.assertIn("commandcode_goat", res)
                                self.assertIn("cline_models", res)
                                self.assertTrue((tmp_data / "benchmarks.json").exists())

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


if __name__ == "__main__":
    unittest.main()
