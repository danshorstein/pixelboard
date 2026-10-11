from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from .diagnostics import run_diagnostics
from .admin_auth import BroadcastPinStore
from .runtime import rehearse_reveal, run_device
from .verification import verify_frames
from shared_py.reveal import RevealTransitionError, arm, disarm, load_reveal, replay, save_reveal


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="scoreboard-device")
    result.add_argument("--root", type=Path, default=Path.cwd(), help="Extracted artifact directory")
    subparsers = result.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Run the standalone scoreboard service")
    run.add_argument("--output", choices=("hub75", "simulator"))
    verify = subparsers.add_parser("verify", help="Render and verify all packaged golden frames")
    verify.add_argument("--output-dir", type=Path)
    diagnose = subparsers.add_parser("diagnose", help="Exercise panel geometry, color channels, and both buttons")
    diagnose.add_argument("--output", choices=("hub75", "simulator"))
    diagnose.add_argument("--step-sec", type=float, default=3.0)
    diagnose.add_argument("--cycles", type=int, default=0, help="Full cycles; zero runs until Ctrl-C")
    rehearse = subparsers.add_parser(
        "rehearse", help="Play the reveal sequence without arming/consuming it — safe to run repeatedly"
    )
    rehearse.add_argument("--output", choices=("hub75", "simulator"))
    reveal = subparsers.add_parser("reveal", help="Operator control of the armed celebration")
    reveal.add_argument("action", choices=("arm", "disarm", "replay", "status"))
    broadcast_pin = subparsers.add_parser("broadcast-pin", help="Show or rotate the household broadcast PIN")
    broadcast_pin.add_argument("action", choices=("show", "rotate"))
    return result


def main() -> int:
    args = parser().parse_args()
    root = args.root.resolve()
    if args.command == "broadcast-pin":
        pins = BroadcastPinStore(root / "state")
        pin = pins.rotate() if args.action == "rotate" else pins.get_or_create()
        print(pin)
        return 0
    if args.command == "verify":
        report = verify_frames(root, (args.output_dir or root / "state" / "verification").resolve())
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "pass" else 1
    if args.command == "reveal":
        reveal_path = root / "state" / "reveal.json"
        current = load_reveal(reveal_path)
        try:
            if args.action == "arm":
                current = arm(current)
                save_reveal(reveal_path, current)
            elif args.action == "disarm":
                current = disarm(current)
                save_reveal(reveal_path, current)
            elif args.action == "replay":
                current = replay(current)
                save_reveal(reveal_path, current)
        except RevealTransitionError as error:
            print(json.dumps({"error": str(error), "state": current.get("state")}))
            return 1
        print(json.dumps(current, indent=2))
        return 0
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.command == "diagnose":
        report = asyncio.run(
            run_diagnostics(root, output_kind=args.output, step_sec=args.step_sec, cycles=max(0, args.cycles))
        )
        print(json.dumps(report, indent=2))
        return 0
    if args.command == "rehearse":
        asyncio.run(rehearse_reveal(root, output_kind=args.output))
        return 0
    asyncio.run(run_device(root, output_kind=args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
