from __future__ import annotations

import hashlib
import unittest

from shared_py.fireworks_frame import create_fireworks_frame

# Computed from frontend/src/fireworks.ts's createFireworksFrame(128, 32, ms)
# for the same elapsedMs values — see docs/STATUS.md for how these were
# cross-checked. Any change to either implementation's math must keep both
# byte-identical.
EXPECTED_SHA256 = {
    0: "8a1c1e16483f5dff3e1d36216db7e4ab8897faa328932117fba7acaf015899de",
    1000: "594628c1a71caed2799f93078f9998b940bda9a4d4678b4bbfef3825d7424c91",
    1800: "5f433431f1f5b326ccf92deddf4c6e754bc38d1e8647e65383e3e49420ec5ed3",
    3599: "89b4ea7066c2e0736c523a3b5fd16cd14b9d9cf57b6ae5200ad096d1e66cce95",
}


class FireworksFrameParityTests(unittest.TestCase):
    def test_frames_are_byte_identical_to_the_typescript_renderer(self) -> None:
        for elapsed_ms, expected in EXPECTED_SHA256.items():
            with self.subTest(elapsedMs=elapsed_ms):
                frame = create_fireworks_frame(128, 32, elapsed_ms)
                self.assertEqual(expected, hashlib.sha256(bytes(frame.data)).hexdigest())


if __name__ == "__main__":
    unittest.main()
