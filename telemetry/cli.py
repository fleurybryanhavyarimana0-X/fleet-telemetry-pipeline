"""Command line entry point: python -m telemetry.cli sample/events.jsonl"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from .pipeline import Rules, run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate and summarize fleet telemetry (JSON Lines).")
    ap.add_argument("path", help="JSON Lines file, one event per line ('-' for stdin)")
    ap.add_argument("--speed-limit", type=float, default=100.0)
    ap.add_argument("--idle-minutes", type=float, default=10.0)
    args = ap.parse_args(argv)

    stream = sys.stdin if args.path == "-" else open(args.path, encoding="utf-8")
    with stream:
        raw = []
        for n, line in enumerate(stream, 1):
            line = line.strip()
            if not line:
                continue
            try:
                raw.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"line {n}: invalid JSON ({exc.msg})", file=sys.stderr)

    result = run(raw, Rules(speed_limit_kph=args.speed_limit, idle_alert_minutes=args.idle_minutes))
    report = {
        "clean_events": len(result.clean),
        "rejected": [{"reason": why, "event_id": r.get("event_id")} for r, why in result.rejected],
        "duplicates": result.duplicates,
        "assets": [asdict(s) for s in result.summaries.values()],
        "alerts": [asdict(a) for a in result.alerts],
    }
    json.dump(report, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
