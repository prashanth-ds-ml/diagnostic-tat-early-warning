from __future__ import annotations

import argparse
import time
from pathlib import Path

from alert_runner import DEFAULT_STATE_FILE, run


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuously score orders and email new alerts.")
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument("--threshold", type=float, default=0.40)
    parser.add_argument("--max-alerts", type=int, default=25)
    parser.add_argument("--all-dates", action="store_true")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument(
        "--send",
        action="store_true",
        help="Send email. Without this flag every cycle is a dry run.",
    )
    args = parser.parse_args()

    while True:
        try:
            run(
                dry_run=not args.send,
                threshold=args.threshold,
                max_alerts=args.max_alerts,
                latest_date_only=not args.all_dates,
                state_file=args.state_file,
            )
        except Exception as exc:
            print(f"Alert cycle failed: {exc}")
        time.sleep(max(args.interval_seconds, 10))


if __name__ == "__main__":
    raise SystemExit(main())

