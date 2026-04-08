from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

CURRENT_FILE = Path(__file__).resolve()
BACKEND_ROOT = CURRENT_FILE.parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal
from app.models.entities import ControlAction, ControlActionEvalJob
from app.services.control_action_learning import control_action_learning_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process pending control-action feedback evaluation jobs")
    parser.add_argument("--batch-size", type=int, default=50, help="Maximum jobs to process per run")
    parser.add_argument("--observation-window-minutes", type=int, default=None, help="Override per-job observation window")
    parser.add_argument("--dry-run", action="store_true", help="Preview pending jobs without updating DB")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    now_dt = datetime.utcnow()
    db = SessionLocal()
    processed = 0
    done = 0
    insufficient = 0
    failed = 0
    try:
        jobs = db.scalars(
            select(ControlActionEvalJob)
            .where(
                ControlActionEvalJob.status == "pending",
                ControlActionEvalJob.scheduled_at <= now_dt,
            )
            .order_by(ControlActionEvalJob.scheduled_at.asc(), ControlActionEvalJob.id.asc())
            .limit(max(1, int(args.batch_size)))
        ).all()
        if not jobs:
            print("[worker] no pending jobs")
            return

        for job in jobs:
            processed += 1
            if args.dry_run:
                print(
                    f"[worker][dry-run] job_id={job.id} action_id={job.control_action_id} "
                    f"device_id={job.device_id} scheduled_at={job.scheduled_at.isoformat()}"
                )
                continue

            job.status = "running"
            job.attempt_count = int(job.attempt_count or 0) + 1
            job.updated_at = datetime.utcnow()
            db.commit()

            action = db.scalar(select(ControlAction).where(ControlAction.id == job.control_action_id))
            if action is None:
                job.status = "failed"
                job.last_error = "control_action_not_found"
                job.updated_at = datetime.utcnow()
                db.commit()
                failed += 1
                continue

            window = args.observation_window_minutes if args.observation_window_minutes is not None else int(job.observation_window_minutes)
            try:
                result = control_action_learning_service.evaluate_control_action(
                    db=db,
                    control_action=action,
                    observation_window_minutes=max(1, int(window)),
                    now_dt=now_dt,
                )
                job.updated_at = datetime.utcnow()
                if result.status == "done":
                    job.status = "done"
                    job.last_error = None
                    done += 1
                elif result.status == "insufficient_data":
                    job.status = "insufficient_data"
                    job.last_error = result.reason
                    insufficient += 1
                else:
                    job.status = "failed"
                    job.last_error = result.reason or "evaluation_failed"
                    failed += 1
                db.commit()
                print(
                    f"[worker] job_id={job.id} action_id={job.control_action_id} status={job.status} "
                    f"sample_id={result.sample_id}"
                )
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                job = db.scalar(select(ControlActionEvalJob).where(ControlActionEvalJob.id == job.id))
                if job is not None:
                    job.status = "failed"
                    job.last_error = str(exc)
                    job.updated_at = datetime.utcnow()
                    db.commit()
                failed += 1
                print(f"[worker] job_id={job.id if job else 'unknown'} failed: {exc}")
    finally:
        db.close()

    print(
        f"[worker] processed={processed} done={done} insufficient={insufficient} failed={failed} dry_run={bool(args.dry_run)}"
    )


if __name__ == "__main__":
    main()

