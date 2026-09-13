#!/usr/bin/env python3
import datetime as dt
import unittest
from unittest.mock import patch, MagicMock

import ocgo


class TestOcgo(unittest.TestCase):
    def test_parse_iso_datetime(self):
        d = ocgo.parse_iso_datetime("2026-09-14T03:44:34.672Z")
        self.assertIsNotNone(d)
        self.assertEqual(d.year, 2026)
        self.assertEqual(d.hour, 3)

    def test_format_relative_time(self):
        now = dt.datetime(2026, 9, 14, 0, 0, 0, tzinfo=dt.timezone.utc)
        target1 = dt.datetime(2026, 9, 14, 2, 30, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(ocgo.format_relative_time(target1, now), "2h 30m")

        target2 = dt.datetime(2026, 9, 17, 5, 0, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(ocgo.format_relative_time(target2, now), "3d 5h")

        past = dt.datetime(2026, 9, 13, 0, 0, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(ocgo.format_relative_time(past, now), "now")

    def test_format_bar(self):
        bar = ocgo.format_bar(50.0, width=10, colorize=False)
        self.assertEqual(bar, "[█████░░░░░]")

    def test_render_statusline(self):
        payload = {
            "usage": {
                "rolling": {"status": "ok", "percent": 5, "resetsAt": "2026-09-14T03:00:00Z"},
                "weekly": {"status": "ok", "percent": 25, "resetsAt": "2026-09-15T00:00:00Z"},
                "monthly": {"status": "ok", "percent": 80, "resetsAt": "2026-09-30T00:00:00Z"},
            }
        }
        res = ocgo.render_statusline(payload)
        self.assertIn("[OpenCode Go]", res)
        self.assertIn("5h: 5%", res)
        self.assertIn("wk: 25%", res)
        self.assertIn("mo: 80%", res)


if __name__ == "__main__":
    unittest.main()
