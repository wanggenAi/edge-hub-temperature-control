from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

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


def process_eval_job(
    *,
    db,
    job: ControlActionEvalJob,
    now_dt: datetime,
    observation_window_override: Optional[int] = None,
) -> str:
    """Process one due eval job and return category:
    done | rescheduled | terminal_insufficient | failed.
    """
    job.status = "running"
    job.attempt_count = int(job.attempt_count or 0) + 1
    job.updated_at = datetime.utcnow()
    db.commit()

    action = db.scalar(select(ControlAction).where(ControlAction.id == job.control_action_id))
    if action is None:
        job.status = "insufficient_data"
        job.last_error = "control_action_not_found"
        job.updated_at = datetime.utcnow()
        db.commit()
        return "terminal_insufficient"

    window = observation_window_override if observation_window_override is not None else int(job.observation_window_minutes)
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
            db.commit()
            print(f"[worker] job_id={job.id} action_id={job.control_action_id} category=done sample_id={result.sample_id}")
            return "done"

        if result.status == "retry_later":
            max_retry = int(control_action_learning_service.policy.max_retry_count)
            retry_delay_minutes = int(control_action_learning_service.policy.retry_delay_minutes)
            if int(job.attempt_count or 0) >= max_retry:
                job.status = "insufficient_data"
                job.last_error = f"retry_exhausted:{result.reason or 'retry_later'}"
                db.commit()
                print(
                    f"[worker] job_id={job.id} action_id={job.control_action_id} "
                    f"category=terminal_insufficient reason={job.last_error}"
                )
                return "terminal_insufficient"

            job.status = "pending"
            job.scheduled_at = now_dt + timedelta(minutes=retry_delay_minutes)
            job.last_error = result.reason or "retry_later"
            db.commit()
            print(
                f"[worker] job_id={job.id} action_id={job.control_action_id} "
                f"category=rescheduled next_at={job.scheduled_at.isoformat()} reason={job.last_error}"
            )
            return "rescheduled"

        if result.status == "terminal_insufficient":
            job.status = "insufficient_data"
            job.last_error = result.reason or "terminal_insufficient"
            db.commit()
            print(
                f"[worker] job_id={job.id} action_id={job.control_action_id} "
                f"category=terminal_insufficient sample_id={result.sample_id} reason={job.last_error}"
            )
            return "terminal_insufficient"

        job.status = "failed"
        job.last_error = result.reason or "evaluation_failed"
        db.commit()
        print(f"[worker] job_id={job.id} action_id={job.control_action_id} category=failed reason={job.last_error}")
        return "failed"
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job_ref = db.scalar(select(ControlActionEvalJob).where(ControlActionEvalJob.id == job.id))
        if job_ref is not None:
            job_ref.status = "failed"
            job_ref.last_error = str(exc)
            job_ref.updated_at = datetime.utcnow()
            db.commit()
        print(f"[worker] job_id={job.id} action_id={job.control_action_id} category=failed reason={exc}")
        return "failed"


def main() -> None:
    args = parse_args()
    now_dt = datetime.utcnow()
    db = SessionLocal()
    processed = 0
    done = 0
    rescheduled = 0
    terminal_insufficient = 0
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

            category = process_eval_job(
                db=db,
                job=job,
                now_dt=now_dt,
                observation_window_override=args.observation_window_minutes,
            )
            if category == "done":
                done += 1
            elif category == "rescheduled":
                rescheduled += 1
            elif category == "terminal_insufficient":
                terminal_insufficient += 1
            else:
                failed += 1
    finally:
        db.close()

    print(
        f"[worker] processed={processed} done={done} rescheduled={rescheduled} "
        f"terminal_insufficient={terminal_insufficient} failed={failed} dry_run={bool(args.dry_run)}"
    )


if __name__ == "__main__":
    main()
