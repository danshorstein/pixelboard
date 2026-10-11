from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shared_py.reveal import (
    RevealTransitionError,
    arm,
    begin_playback,
    complete_playback,
    default_reveal,
    disarm,
    force_start,
    load_reveal,
    replay,
    save_reveal,
    should_autoplay_on_boot,
)


class RevealStateMachineTests(unittest.TestCase):
    def test_default_state_is_disarmed_and_does_not_autoplay(self) -> None:
        self.assertEqual(default_reveal()["state"], "disarmed")
        self.assertFalse(should_autoplay_on_boot(default_reveal()))

    def test_full_lifecycle_arm_start_complete_replay(self) -> None:
        reveal = default_reveal()
        reveal = arm(reveal)
        self.assertTrue(should_autoplay_on_boot(reveal))
        reveal = begin_playback(reveal)
        self.assertEqual(reveal["state"], "started")
        self.assertFalse(should_autoplay_on_boot(reveal))
        reveal = complete_playback(reveal)
        self.assertEqual(reveal["state"], "completed")
        reveal = replay(reveal)
        self.assertEqual(reveal["state"], "started")

    def test_illegal_transitions_are_rejected(self) -> None:
        with self.assertRaises(RevealTransitionError):
            begin_playback(default_reveal())  # disarmed -> started is not allowed
        with self.assertRaises(RevealTransitionError):
            disarm(default_reveal())  # disarmed -> disarmed is not a transition
        with self.assertRaises(RevealTransitionError):
            complete_playback(arm(default_reveal()))  # armed -> completed skips started

    def test_force_start_works_from_any_state_unlike_begin_playback_or_replay(self) -> None:
        for reveal in (default_reveal(), arm(default_reveal())):
            self.assertEqual(force_start(reveal)["state"], "started")
        completed = complete_playback(begin_playback(arm(default_reveal())))
        self.assertEqual(force_start(completed)["state"], "started")
        self.assertEqual(force_start(completed)["state"], force_start(force_start(completed))["state"])

    def test_power_loss_after_started_is_written_does_not_cause_an_endless_replay(self) -> None:
        """The exact crash scenario the plan calls out: mark started durably
        before playback, so an interruption there does not re-arm anything."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "reveal.json"
            reveal = arm(default_reveal())
            save_reveal(path, reveal)
            self.assertTrue(should_autoplay_on_boot(load_reveal(path)))

            # Playback begins: state is persisted BEFORE any frame renders.
            reveal = begin_playback(reveal)
            save_reveal(path, reveal)

            # Power is lost here — simulate a fresh process reading the state.
            reloaded = load_reveal(path)
            self.assertEqual(reloaded["state"], "started")
            self.assertFalse(should_autoplay_on_boot(reloaded))
            # A second "boot" reads the same file again — still no autoplay.
            self.assertFalse(should_autoplay_on_boot(load_reveal(path)))

    def test_load_reveal_fails_closed_to_disarmed_on_corrupt_or_missing_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "reveal.json"
            self.assertEqual(load_reveal(missing)["state"], "disarmed")

            corrupt = Path(directory) / "corrupt.json"
            corrupt.write_text("not json", encoding="utf-8")
            self.assertEqual(load_reveal(corrupt)["state"], "disarmed")

            invalid_state = Path(directory) / "invalid.json"
            invalid_state.write_text(json.dumps({"state": "on-fire"}), encoding="utf-8")
            self.assertEqual(load_reveal(invalid_state)["state"], "disarmed")

    def test_save_reveal_is_atomic_and_does_not_leave_a_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "reveal.json"
            save_reveal(path, arm(default_reveal()))
            self.assertTrue(path.is_file())
            self.assertFalse(path.with_suffix(".tmp").exists())

    def test_ordinary_boot_never_arms_on_its_own(self) -> None:
        # Nothing in this module's public API can move a fresh/disarmed
        # reveal to "armed" except the explicit arm() call — a boot sequence
        # that only calls load_reveal/should_autoplay_on_boot can never
        # arm it as a side effect.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reveal.json"
            for _ in range(5):
                reveal = load_reveal(path)
                self.assertFalse(should_autoplay_on_boot(reveal))
                save_reveal(path, reveal)


if __name__ == "__main__":
    unittest.main()
