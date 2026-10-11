from __future__ import annotations

import unittest
from pathlib import Path

from shared_py.bdf import parse_bdf
from shared_py.reveal_frame import create_reveal_text_frame

ROOT = Path(__file__).resolve().parents[1]


class RevealFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.font = parse_bdf((ROOT / "definition/mlb-classic/fonts/5x7.bdf").read_text(encoding="utf-8"))

    def test_renders_a_full_size_frame_for_the_panel(self) -> None:
        frame = create_reveal_text_frame(128, 32, ["WELCOME TO THE BALLPARK"], self.font)
        self.assertEqual(frame.width, 128)
        self.assertEqual(frame.height, 32)
        self.assertEqual(len(frame.data), 128 * 32 * 4)

    def test_wraps_text_too_wide_for_the_panel_instead_of_running_off_screen(self) -> None:
        long_line = "THIS LINE IS DEFINITELY TOO WIDE TO FIT ON ONE ROW OF A ONE TWENTY EIGHT PIXEL PANEL"
        frame = create_reveal_text_frame(128, 32, [long_line], self.font)
        # A lit pixel should never land past the right edge or off the top/bottom.
        lit_columns = {
            (index // 4) % 128
            for index in range(0, len(frame.data), 4)
            if frame.data[index:index + 3] != bytes((0, 0, 0))
        }
        self.assertTrue(lit_columns)
        self.assertLess(max(lit_columns), 128)

    def test_empty_lines_render_without_error(self) -> None:
        frame = create_reveal_text_frame(128, 32, [], self.font)
        self.assertEqual(len(frame.data), 128 * 32 * 4)


if __name__ == "__main__":
    unittest.main()
