from __future__ import annotations

import argparse
import sys
from pathlib import Path

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.services.seed import seed_database


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed HMI backend relational data")
    parser.add_argument("--rules", action="store_true", help="Seed default alarm rules")
    parser.add_argument("--demo", action="store_true", help="Seed demo users/devices/metrics")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if not args.rules and not args.demo:
        raise SystemExit("No seed action selected. Use --rules and/or --demo.")

    db = SessionLocal()
    try:
        seed_database(db, with_default_alarm_rules=args.rules, with_demo_data=args.demo)
    finally:
        db.close()

    print(f"Seed completed (rules={args.rules}, demo={args.demo}).")
