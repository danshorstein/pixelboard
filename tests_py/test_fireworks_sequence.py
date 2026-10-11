from __future__ import annotations

import unittest

from shared_py.fireworks_sequence import FIREWORKS_SEQUENCE, advance_secret_sequence


class FireworksSequenceTests(unittest.TestCase):
    """Mirrors frontend/src/easterEgg.test.ts for TS/Python parity."""

    def test_recognizes_next_three_times_hold_three_times_then_next_three_times(self) -> None:
        progress = 0
        for press in FIREWORKS_SEQUENCE:
            progress = advance_secret_sequence(progress, press)
        self.assertEqual(progress, len(FIREWORKS_SEQUENCE))

    def test_resets_the_sequence_after_an_incorrect_press_while_allowing_a_new_next_start(self) -> None:
        self.assertEqual(advance_secret_sequence(3, "next"), 1)
        self.assertEqual(advance_secret_sequence(3, "hold"), 4)


if __name__ == "__main__":
    unittest.main()
