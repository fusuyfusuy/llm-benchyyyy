#!/usr/bin/env python3
import datetime as dt
import unittest
from unittest.mock import patch, MagicMock

import ccgo


class TestCcgo(unittest.TestCase):
    def test_format_relative_seconds(self):
        self.assertEqual(ccgo.format_relative_seconds(0), "now")
        self.assertEqual(ccgo.format_relative_seconds(-10), "now")
        self.assertEqual(ccgo.format_relative_seconds(120), "2m")
        self.assertEqual(ccgo.format_relative_seconds(3700), "1h 1m")
        self.assertEqual(ccgo.format_relative_seconds(90000), "1d 1h")

    def test_format_tokens(self):
        self.assertEqual(ccgo.format_tokens(500), "500")
        self.assertEqual(ccgo.format_tokens(1500), "1.5k")
        self.assertEqual(ccgo.format_tokens(2500000), "2.50M")
        self.assertEqual(ccgo.format_tokens(1450000000), "1.45B")

    def test_format_bar(self):
        bar = ccgo.format_bar(30.0, width=10, colorize=False)
        self.assertEqual(bar, "[███░░░░░░░]")

    def test_render_statusline(self):
        telemetry = {
            "subscriptions": {"data": {"planId": "individual-goat"}},
            "credits": {
                "credits": {"monthlyCredits": 15.5},
                "windowLimits": {
                    "fiveHour": {"used": 2.0, "cap": 14.0, "resetAt": 1789346104765},
                    "weekly": {"used": 10.0, "cap": 35.0, "resetAt": 1789470391006},
                },
            },
        }
        res = ccgo.render_statusline(telemetry)
        self.assertIn("[CommandCode Individual GOAT]", res)
        self.assertIn("5h: $2.00/14", res)
        self.assertIn("wk: $10.00/35", res)
        self.assertIn("$15.50 left", res)


if __name__ == "__main__":
    unittest.main()
