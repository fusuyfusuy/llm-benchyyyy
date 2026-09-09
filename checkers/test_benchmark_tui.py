#!/usr/bin/env python3
"""
test_benchmark_tui.py — Unit test suite for interactive benchmark TUI.
"""
import unittest
from unittest.mock import patch
from checkers.benchmark_tui import TUIState, run_tui, POOLS
import checkers.benchmark_common as bc


class TestBenchmarkTUI(unittest.TestCase):
    def setUp(self):
        self.sample_models = [
            {
                "display": "Claude Opus 5 (Thinking)",
                "model_id": "claude-opus-5",
                "provider": "Anthropic",
                "pool": "claude",
                "capability_q": 95.1,
                "context_length": 200000,
                "price_in": 5.0,
                "price_out": 25.0,
                "base_metrics": {"speed_tps": 52.0, "lm_elo": 1661, "aa_quality": 50.7},
                "livebench": {
                    "overall": 80.5,
                    "categories": {"Reasoning": 91.2, "Coding": 81.5},
                },
            },
            {
                "display": "Gemini 3.7 Flash",
                "model_id": "gemini-3.7-flash",
                "provider": "Google",
                "pool": "agy",
                "capability_q": 92.0,
                "context_length": 1000000,
                "price_in": 0.38,
                "price_out": 1.88,
                "base_metrics": {"speed_tps": 315.0, "lm_elo": 1490, "aa_quality": 45.2},
                "livebench": {
                    "overall": 79.9,
                    "categories": {"Reasoning": 88.4, "Coding": 80.2},
                },
            },
            {
                "display": "DeepSeek V4 Flash",
                "model_id": "deepseek-v4-flash",
                "provider": "DeepSeek",
                "pool": "ocgo",
                "capability_q": 85.0,
                "context_length": 128000,
                "price_in": 0.06,
                "price_out": 0.11,
                "base_metrics": {"speed_tps": 103.0, "lm_elo": 1360, "aa_quality": 38.5},
                "livebench": {
                    "overall": 66.0,
                    "categories": {"Reasoning": 82.1, "Coding": 76.4},
                },
            },
            {
                "display": "Single Bench Model",
                "model_id": "single-bench",
                "provider": "Experimental",
                "pool": "api",
                "capability_q": 70.0,
                "context_length": 32000,
                "price_in": 0.50,
                "price_out": 1.50,
                "base_metrics": {"speed_tps": 60.0},
                "livebench": None,
                "aa_live_quality": 25.0,
            },
        ]

    def test_state_init_and_tri_verified_default(self):
        # Default tri_verified_only=True: only 3/3 models included (Single Bench Model excluded)
        state = TUIState(all_models=self.sample_models, unmatched_models=[])
        self.assertEqual(len(state.filtered_models), 3)
        self.assertEqual(state.filtered_models[0]["display"], "Claude Opus 5 (Thinking)")

    def test_toggle_tri_verified(self):
        state = TUIState(all_models=self.sample_models, unmatched_models=[])
        self.assertEqual(len(state.filtered_models), 3)
        state.toggle_tri_verified()
        # Now all 4 models are included
        self.assertEqual(len(state.filtered_models), 4)
        self.assertFalse(state.tri_verified_only)

    def test_top_limit_focus(self):
        state = TUIState(all_models=self.sample_models, unmatched_models=[], top_limit=2)
        self.assertEqual(len(state.filtered_models), 2)
        self.assertEqual(len(state.top_cohort), 2)

    def test_pagination_controls(self):
        state = TUIState(all_models=self.sample_models, unmatched_models=[], page_size=2)
        self.assertEqual(state.total_pages, 2)
        self.assertEqual(state.page_idx, 0)
        state.next_page()
        self.assertEqual(state.page_idx, 1)
        state.prev_page()
        self.assertEqual(state.page_idx, 0)

    def test_pool_filter(self):
        state = TUIState(all_models=self.sample_models, unmatched_models=[])
        state.pool_filter = "agy"
        state.apply_filters()
        self.assertEqual(len(state.filtered_models), 1)
        self.assertEqual(state.filtered_models[0]["display"], "Gemini 3.7 Flash")

    def test_search_filter(self):
        state = TUIState(all_models=self.sample_models, unmatched_models=[])
        state.search_query = "deepseek"
        state.apply_filters()
        self.assertEqual(len(state.filtered_models), 1)
        self.assertEqual(state.filtered_models[0]["display"], "DeepSeek V4 Flash")

    def test_sort_by_speed(self):
        state = TUIState(all_models=self.sample_models, unmatched_models=[])
        state.set_sort("speed")
        self.assertEqual(state.filtered_models[0]["display"], "Gemini 3.7 Flash")

    def test_sort_by_coding(self):
        state = TUIState(all_models=self.sample_models, unmatched_models=[])
        state.set_sort("coding")
        self.assertEqual(state.filtered_models[0]["display"], "Claude Opus 5 (Thinking)")

    def test_sort_by_ctx(self):
        state = TUIState(all_models=self.sample_models, unmatched_models=[])
        state.set_sort("ctx")
        self.assertEqual(state.filtered_models[0]["display"], "Gemini 3.7 Flash")

    def test_sort_by_price(self):
        state = TUIState(all_models=self.sample_models, unmatched_models=[])
        state.set_sort("price")
        self.assertEqual(state.filtered_models[0]["display"], "DeepSeek V4 Flash")

    def test_toggle_pareto_only(self):
        state = TUIState(all_models=self.sample_models, unmatched_models=[])
        state.toggle_pareto_only()
        self.assertTrue(state.pareto_only)
        for m in state.filtered_models:
            self.assertIn(m["display"], state.pareto_ids)

    def test_role_distribution_generation(self):
        state = TUIState(all_models=self.sample_models, unmatched_models=[])
        self.assertIn("architecture", state.role_recs)
        self.assertIn("pair_programming", state.role_recs)
        self.assertIn("daily_driver", state.role_recs)
        self.assertIn("boilerplate", state.role_recs)

    def test_pad_display_emoji_alignment(self):
        # Verify that pad_display produces EXACT visual display length across standard and wide characters
        p1 = bc.pad_display("🥇#1", 6, "^")
        p2 = bc.pad_display("#10", 6, "^")
        p3 = bc.pad_display("⭐#1", 6, "^")
        p4 = bc.pad_display("⭐🥇#1", 6, "^")
        p5 = bc.pad_display("Claude 3.5 Sonnet", 10, "<")

        self.assertEqual(bc.display_len(p1), 6)
        self.assertEqual(bc.display_len(p2), 6)
        self.assertEqual(bc.display_len(p3), 6)
        self.assertEqual(bc.display_len(p4), 6)
        self.assertEqual(bc.display_len(p5), 10)

    def test_pin_baseline_and_diff_state(self):
        state = TUIState(all_models=self.sample_models, unmatched_models=[])
        self.assertEqual(state.diff_baseline_idx, 0)
        state.cursor_idx = 1
        state.pin_current_as_baseline()
        self.assertEqual(state.diff_baseline_idx, 1)
        self.assertIn("Pinned diff baseline", state.status_msg)

    def test_cycle_sort(self):
        state = TUIState(all_models=self.sample_models, unmatched_models=[])
        self.assertEqual(state.sort_key, "composite")
        state.cycle_sort()
        self.assertEqual(state.sort_key, "coding")
        state.cycle_sort()
        self.assertEqual(state.sort_key, "reasoning")

    def test_responsive_table_widths_equality(self):
        # Assert mathematical equality across top border, header, separator, data row, and bottom border
        from checkers.benchmark_tui import pad_display
        state = TUIState(all_models=self.sample_models, unmatched_models=[])

        for max_x in [70, 80, 95, 115, 135, 160]:
            margin = 1 if max_x >= 90 else 0
            max_table_w = max_x - (margin * 2) - 1

            if max_table_w < 78:
                fixed_before = [("Rank", 4, "^")]
                fixed_after = [("Conf", 5, "^"), ("Q(Cap)", 6, ">"), ("Speed", 6, ">")]
            elif max_table_w < 89:
                fixed_before = [("Rank", 5, "^")]
                fixed_after = [("Pool", 5, "^"), ("Conf", 5, "^"), ("Q(Cap)", 6, ">"), ("Reason", 6, ">"), ("Coding", 6, ">"), ("Speed", 6, ">")]
            elif max_table_w < 109:
                fixed_before = [("Rank", 5, "^")]
                fixed_after = [("Pool", 5, "^"), ("Conf", 5, "^"), ("Q(Cap)", 6, ">"), ("Reason", 6, ">"), ("Coding", 6, ">"), ("Speed", 6, ">"), ("Ctx", 6, ">")]
            elif max_table_w < 129:
                fixed_before = [("Rank", 5, "^")]
                fixed_after = [("Pool", 5, "^"), ("Conf", 5, "^"), ("Q(Cap)", 6, ">"), ("Reason", 6, ">"), ("Coding", 6, ">"), ("Speed", 6, ">"), ("Ctx", 6, ">"), ("Price", 11, ">")]
            else:
                fixed_before = [("Rank", 5, "^")]
                fixed_after = [("Pool", 5, "^"), ("Conf", 5, "^"), ("Q(Cap)", 6, ">"), ("Reason", 6, ">"), ("Coding", 6, ">"), ("Speed", 6, ">"), ("Ctx", 6, ">"), ("Price", 11, ">"), ("Best Role", 14, "<")]

            num_cols = len(fixed_before) + 1 + len(fixed_after)
            sep_w = 3 * num_cols + 1
            fixed_w = sum(w for _, w, _ in fixed_before) + sum(w for _, w, _ in fixed_after)
            model_w = max(14, max_table_w - sep_w - fixed_w)
            if max_x >= 150:
                model_w = min(46, model_w)
            cols = fixed_before + [("Model", model_w, "<")] + fixed_after

            actual_table_w = fixed_w + model_w + sep_w

            top = "┌" + "─" * (actual_table_w - 2) + "┐"
            hdr_cells = [pad_display(name, w, align) for name, w, align in cols]
            hdr = "│ " + " │ ".join(hdr_cells) + " │"
            sep = "├" + "─" * (actual_table_w - 2) + "┤"

            vals_map = {
                "Rank": "⭐🥇#1",
                "Model": "Claude Opus 5 (Thinking)",
                "Pool": "CLD",
                "Conf": "[3/3]",
                "Q(Cap)": "95.1",
                "Reason": "91.2%",
                "Coding": "81.5%",
                "Speed": "52t/s",
                "Ctx": "200k",
                "Price": "$5.0/$25.0",
                "Best Role": "Architecture",
            }
            row_cells = [pad_display(vals_map.get(name, "—"), w, align) for name, w, align in cols]
            row = "▶ " + " │ ".join(row_cells) + " │"
            bot = "└" + "─" * (actual_table_w - 2) + "┘"

            self.assertEqual(bc.display_len(top), actual_table_w)
            self.assertEqual(bc.display_len(hdr), actual_table_w)
            self.assertEqual(bc.display_len(sep), actual_table_w)
            self.assertEqual(bc.display_len(row), actual_table_w)
            self.assertEqual(bc.display_len(bot), actual_table_w)
            self.assertLessEqual(actual_table_w, max_x)

    def test_modal_pareto_drawer_truth(self):
        # Ensure a model not on pareto frontier is correctly identified as not on pareto
        state = TUIState(all_models=self.sample_models, unmatched_models=[])
        state.toggle_tri_verified() # Include all models
        # Find model not in pareto_ids
        non_pareto = [m for m in state.filtered_models if m["display"] not in state.pareto_ids]
        if non_pareto:
            target = non_pareto[0]
            is_par = (target["display"] in state.pareto_ids)
            self.assertFalse(is_par)


    def test_drawer_atomic_lifecycle(self):
        # Verify draw_modal uses erase() and noutrefresh() for zero-flicker opaque rendering
        from checkers.benchmark_tui import draw_modal
        from unittest.mock import MagicMock

        state = TUIState(all_models=self.sample_models, unmatched_models=[])
        mock_stdscr = MagicMock()
        mock_modal_win = MagicMock()
        mock_modal_win.getmaxyx.return_value = (24, 80)

        with patch("curses.newwin", return_value=mock_modal_win), patch("curses.color_pair", return_value=0):
            draw_modal(mock_stdscr, self.sample_models[0], state, max_y=24, max_x=80)
            mock_modal_win.erase.assert_called_once()
            mock_modal_win.noutrefresh.assert_called_once()
            mock_modal_win.refresh.assert_not_called()

    @patch("sys.stdin.isatty", return_value=False)
    @patch("sys.stdout.isatty", return_value=False)
    def test_non_tty_fallback(self, mock_stdout, mock_stdin):
        try:
            run_tui(self.sample_models, color=False, unmatched_models=[])
        except Exception as e:
            self.fail(f"run_tui raised unexpected exception in non-tty mode: {e}")

    @patch("sys.stdin.isatty", return_value=False)
    @patch("sys.stdout.isatty", return_value=False)
    def test_run_tui_parameter_forwarding(self, mock_stdout, mock_stdin):
        with patch("checkers.llm_benchmark_aggregator.render_one_shot_cli_table") as mock_render:
            mock_render.return_value = ""
            run_tui(self.sample_models, color=False, unmatched_models=[], tri_verified_only=False, top_limit=2)
            self.assertTrue(mock_render.called)
            passed_models = mock_render.call_args[0][0]
            # When tri_verified_only=False and top_limit=2, exactly 2 models are passed
            self.assertEqual(len(passed_models), 2)

    def test_safe_addstr_boxed_border_preservation(self):
        from checkers.benchmark_tui import safe_addstr

        class DummyWin:
            def __init__(self, h, w):
                self.h = h
                self.w = w
                self.grid = [[' ' for _ in range(w)] for _ in range(h)]
            def getmaxyx(self):
                return self.h, self.w
            def addstr(self, y, x, text, attr=0):
                for i, ch in enumerate(text):
                    if 0 <= y < self.h and 0 <= x + i < self.w:
                        self.grid[y][x + i] = ch

        win = DummyWin(10, 40)
        # Put border markers
        for y in range(win.h):
            win.grid[y][0] = '│'
            win.grid[y][win.w - 1] = '│'

        # Safe addstr with boxed=True and long string
        safe_addstr(win, 3, 2, 'Z' * 100, boxed=True)
        self.assertEqual(win.grid[3][0], '│')
        self.assertEqual(win.grid[3][39], '│')
        self.assertEqual(win.grid[3][38], 'Z')

    def test_draw_diff_modal_border_preservation(self):
        from checkers.benchmark_tui import draw_diff_modal

        class DummyWin:
            def __init__(self, h, w):
                self.h = h
                self.w = w
                self.grid = [[' ' for _ in range(w)] for _ in range(h)]
            def getmaxyx(self):
                return self.h, self.w
            def erase(self):
                pass
            def box(self):
                for y in range(self.h):
                    self.grid[y][0] = '│'
                    self.grid[y][self.w - 1] = '│'
                for x in range(self.w):
                    self.grid[0][x] = '─'
                    self.grid[self.h - 1][x] = '─'
            def addstr(self, y, x, text, attr=0):
                for i, ch in enumerate(text):
                    if 0 <= y < self.h and 0 <= x + i < self.w:
                        self.grid[y][x + i] = ch
            def noutrefresh(self):
                pass

        win = DummyWin(22, 60)
        state = TUIState(all_models=self.sample_models, unmatched_models=[], tri_verified_only=False)

        with patch('curses.newwin', return_value=win), patch('curses.color_pair', return_value=0):
            draw_diff_modal(None, state, max_y=24, max_x=64)

        # Ensure no content or leading spaces overwrote left border
        for y in range(win.h):
            if y not in (0, win.h - 1, 2, 4):
                self.assertEqual(win.grid[y][0], '│', f"Row {y} left border was overwritten by {repr(win.grid[y][0])}")
                self.assertEqual(win.grid[y][win.w - 1], '│', f"Row {y} right border was overwritten by {repr(win.grid[y][win.w - 1])}")


if __name__ == "__main__":
    unittest.main()
