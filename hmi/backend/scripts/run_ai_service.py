#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run standalone AI runtime service")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8010, help="Bind port")
    parser.add_argument("--reload", action="store_true", help="Enable autoreload")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    uvicorn.run(
        "app.ai_service_app:app",
        host=str(args.host),
        port=int(args.port),
        reload=bool(args.reload),
        log_level="info",
    )


if __name__ == "__main__":
    main()

