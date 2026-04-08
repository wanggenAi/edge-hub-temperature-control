from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.entities import (
    AIRecommendation,
    ControlAction,
    ControlActionEvalJob,
    ControlActionFeedbackSample,
    Device,
    DeviceMetric,
    DeviceParameter,
)
from app.services.control_action_learning import (
    _derive_quality,
    control_action_learning_service,
)
from scripts.run_control_action_feedback_worker import process_eval_job


class ControlActionLearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        tag = uuid4().hex[:8]
        self.device = Device(
            code=f"UT-CA-{tag}",
            name="UT Control Action Device",
            line="UT",
            location="UT",
            status="active",
            current_temp=37.0,
            target_temp=37.0,
            pwm_output=50.0,
            is_alarm=False,
            is_online=True,
        )
        self.db.add(self.device)
        self.db.flush()
        self.param = DeviceParameter(
            device_id=self.device.id,
            kp=2.2,
            ki=0.3,
            kd=0.1,
            control_mode="pid_control",
            target_band=0.5,
            steady_window_samples=12,
            overshoot_limit_pct=3.0,
            saturation_warn_ratio=0.3,
            saturation_high_ratio=0.6,
            pwm_saturation_threshold=85.0,
            updated_by="unittest",
        )
        self.db.add(self.param)
        self.db.commit()

    def tearDown(self) -> None:
        try:
            self.db.execute(delete(ControlActionFeedbackSample).where(ControlActionFeedbackSample.device_id == self.device.id))
            self.db.execute(delete(ControlActionEvalJob).where(ControlActionEvalJob.device_id == self.device.id))
            self.db.execute(delete(ControlAction).where(ControlAction.device_id == self.device.id))
            self.db.execute(delete(AIRecommendation).where(AIRecommendation.device_id == self.device.id))
            self.db.execute(delete(DeviceMetric).where(DeviceMetric.device_id == self.device.id))
            self.db.execute(delete(DeviceParameter).where(DeviceParameter.device_id == self.device.id))
            self.db.execute(delete(Device).where(Device.id == self.device.id))
            self.db.commit()
        finally:
            self.db.close()

    def _make_ai_suggestion(self, primary_problem_type: str) -> str:
        payload = {
            "f": "ai_rec",
            "v": "2",
            "p": {
                "t": primary_problem_type,
                "pt": primary_problem_type,
                "st": [],
                "pf": {},
                "e": "keep_stable",
                "r": "Low",
                "c": 0.8,
                "rc": False,
                "cp": {"kp": 2.2, "ki": 0.3, "kd": 0.1},
                "rp": {"kp": 2.1, "ki": 0.28, "kd": 0.12},
                "d": {"kp": -0.1, "ki": -0.02, "kd": 0.02},
                "evidence": {},
                "m": {},
            },
        }
        return json.dumps(payload, separators=(",", ":"))

    def _create_ai_recommendation(self, primary_problem_type: str = "normal") -> AIRecommendation:
        rec = AIRecommendation(
            device_id=self.device.id,
            reason=f"{primary_problem_type}; effect=keep_stable",
            suggestion=self._make_ai_suggestion(primary_problem_type),
            confidence=0.8,
            risk="Low; requires_confirmation=False",
            last_run_at=datetime.utcnow(),
        )
        self.db.add(rec)
        self.db.commit()
        self.db.refresh(rec)
        return rec

    def _create_action(
        self,
        *,
        source: str,
        source_ref_id: int | None = None,
        applied_at: datetime | None = None,
        observation_window_minutes: int | None = None,
        scheduled_at: datetime | None = None,
        context_snapshot: dict | None = None,
    ) -> tuple[ControlAction, ControlActionEvalJob]:
        return control_action_learning_service.create_action_and_eval_job(
            db=self.db,
            device=self.device,
            source=source,
            source_ref_id=source_ref_id,
            action_type="pid_apply",
            initiated_by="operator1",
            applied_at=applied_at or datetime.utcnow(),
            before={"control_mode": "pid_control", "target_temp": 37.0, "kp": 2.2, "ki": 0.3, "kd": 0.1},
            after={"control_mode": "pid_control", "target_temp": 37.0, "kp": 2.4, "ki": 0.34, "kd": 0.12},
            context_snapshot=context_snapshot or {},
            observation_window_minutes=observation_window_minutes,
            scheduled_at=scheduled_at,
        )

    def _insert_metrics(
        self,
        *,
        apply_at: datetime,
        before_count: int = 20,
        after_count: int = 20,
        target_shift: float = 0.0,
        offline_after_ratio: float = 0.0,
    ) -> None:
        for i in range(before_count):
            ts = apply_at - timedelta(minutes=20) + timedelta(seconds=i * 45)
            temp = 36.6 + 0.02 * i
            err = temp - 37.0
            self.db.add(
                DeviceMetric(
                    device_id=self.device.id,
                    timestamp=ts,
                    current_temp=temp,
                    target_temp=37.0,
                    error=err,
                    pwm_output=58.0,
                    status="active",
                    in_spec=abs(err) <= 0.5,
                    is_alarm=False,
                )
            )
        for i in range(after_count):
            ts = apply_at + timedelta(seconds=i * 45)
            temp = 36.9 + 0.004 * i
            target = 37.0 + target_shift
            err = temp - target
            status = "offline" if i < int(after_count * offline_after_ratio) else "active"
            self.db.add(
                DeviceMetric(
                    device_id=self.device.id,
                    timestamp=ts,
                    current_temp=temp,
                    target_temp=target,
                    error=err,
                    pwm_output=52.0,
                    status=status,
                    in_spec=abs(err) <= 0.5,
                    is_alarm=False,
                )
            )
        self.db.commit()

    def test_new_eval_job_scheduled_after_observation_window_manual_default(self) -> None:
        apply_at = datetime.utcnow()
        _action, job = self._create_action(source="manual_user", applied_at=apply_at)
        self.assertEqual(job.observation_window_minutes, 20)
        delta = job.scheduled_at - apply_at
        self.assertAlmostEqual(delta.total_seconds(), 20 * 60, delta=3)

    def test_new_eval_job_scheduled_after_observation_window_ai_policy(self) -> None:
        rec = self._create_ai_recommendation("slow_response")
        apply_at = datetime.utcnow()
        _action, job = self._create_action(source="ai_recommendation", source_ref_id=rec.id, applied_at=apply_at)
        self.assertEqual(job.observation_window_minutes, 25)
        delta = job.scheduled_at - apply_at
        self.assertAlmostEqual(delta.total_seconds(), 25 * 60, delta=3)

    def test_worker_reschedules_too_early_jobs_and_increments_retry(self) -> None:
        apply_at = datetime.utcnow()
        _action, job = self._create_action(
            source="manual_user",
            applied_at=apply_at,
            scheduled_at=apply_at,
            observation_window_minutes=20,
        )
        category = process_eval_job(db=self.db, job=job, now_dt=apply_at)
        self.assertEqual(category, "rescheduled")
        self.db.refresh(job)
        self.assertEqual(job.status, "pending")
        self.assertEqual(job.attempt_count, 1)
        self.assertGreater(job.scheduled_at, apply_at)

    def test_worker_retry_exhaustion_causes_terminal_status(self) -> None:
        apply_at = datetime.utcnow()
        _action, job = self._create_action(
            source="manual_user",
            applied_at=apply_at,
            scheduled_at=apply_at,
            observation_window_minutes=20,
        )
        job.attempt_count = control_action_learning_service.policy.max_retry_count
        self.db.commit()

        category = process_eval_job(db=self.db, job=job, now_dt=apply_at)
        self.assertEqual(category, "terminal_insufficient")
        self.db.refresh(job)
        self.assertEqual(job.status, "insufficient_data")
        self.assertIn("retry_exhausted", str(job.last_error))

    def test_manual_origin_sample_persists_pre_action_feature_snapshot(self) -> None:
        apply_at = datetime.utcnow() - timedelta(minutes=30)
        action, _job = self._create_action(
            source="manual_user",
            applied_at=apply_at,
            observation_window_minutes=20,
            scheduled_at=apply_at,
        )
        self._insert_metrics(apply_at=apply_at, before_count=30, after_count=30)

        result = control_action_learning_service.evaluate_control_action(
            db=self.db,
            control_action=action,
            observation_window_minutes=20,
            now_dt=datetime.utcnow(),
        )
        self.assertEqual(result.status, "done")
        sample = self.db.scalar(
            select(ControlActionFeedbackSample).where(ControlActionFeedbackSample.control_action_id == action.id)
        )
        self.assertIsNotNone(sample)
        assert sample is not None
        self.assertIsNotNone(sample.mean_error)
        self.assertIsNotNone(sample.mean_abs_error)
        self.assertIsNotNone(sample.error_std)
        self.assertIsNotNone(sample.temp_swing)
        self.assertIsNotNone(sample.pwm_mean)
        self.assertIsNotNone(sample.in_band_ratio)

    def test_sample_quality_and_eligibility_policy(self) -> None:
        self.assertEqual(_derive_quality(insufficient_data=False, reasons=[]), ("high", True, None))
        self.assertEqual(_derive_quality(insufficient_data=False, reasons=["baseline_unavailable"]), ("medium", True, "baseline_unavailable"))
        low_quality = _derive_quality(insufficient_data=False, reasons=["baseline_unavailable", "minor_noise"]) 
        self.assertEqual(low_quality[0], "low")
        self.assertFalse(low_quality[1])
        reject_quality = _derive_quality(insufficient_data=True, reasons=["not_enough_post_apply_points"])
        self.assertEqual(reject_quality[0], "reject")
        self.assertFalse(reject_quality[1])

    def test_existing_ai_origin_sample_flow_still_works(self) -> None:
        rec = self._create_ai_recommendation("oscillation")
        apply_at = datetime.utcnow() - timedelta(minutes=40)
        action, _job = self._create_action(
            source="ai_recommendation",
            source_ref_id=rec.id,
            applied_at=apply_at,
            observation_window_minutes=12,
            scheduled_at=apply_at,
        )
        self._insert_metrics(apply_at=apply_at, before_count=25, after_count=25)

        result = control_action_learning_service.evaluate_control_action(
            db=self.db,
            control_action=action,
            observation_window_minutes=12,
            now_dt=datetime.utcnow(),
        )
        self.assertEqual(result.status, "done")
        sample = self.db.scalar(
            select(ControlActionFeedbackSample).where(ControlActionFeedbackSample.control_action_id == action.id)
        )
        self.assertIsNotNone(sample)
        assert sample is not None
        self.assertEqual(sample.source, "ai_recommendation")


if __name__ == "__main__":
    unittest.main()
