#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import time

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.ai.model_lifecycle_service import model_lifecycle_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Periodic candidate-training + promote-gate worker")
    parser.add_argument("--once", action="store_true", help="Run one lifecycle check and exit")
    parser.add_argument("--dry-run", action="store_true", help="Compare and gate only; never promote to active")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=max(30, int(settings.model_lifecycle_check_interval_seconds)),
        help="Polling interval in seconds (used when --once is not set)",
    )
    return parser.parse_args()


def run_once(*, dry_run: bool) -> None:
    db = SessionLocal()
    try:
        result = model_lifecycle_service.run_lifecycle(db, trigger_source="scheduled", dry_run=dry_run)
        print(f"[model-lifecycle] ts={datetime.utcnow().isoformat()} result={result}")
    finally:
        db.close()


def main() -> None:
    args = parse_args()
    if not settings.model_lifecycle_enabled:
        print("[model-lifecycle] disabled by config (model_lifecycle_enabled=false)")
        return
    if args.once:
        run_once(dry_run=bool(args.dry_run))
        return

    interval = max(30, int(args.interval_seconds))
    print(f"[model-lifecycle] worker started interval_seconds={interval} dry_run={bool(args.dry_run)}")
    while True:
        try:
            run_once(dry_run=bool(args.dry_run))
        except Exception as exc:
            print(f"[model-lifecycle] run failed: {exc}")
        time.sleep(interval)


if __name__ == "__main__":
    main()

