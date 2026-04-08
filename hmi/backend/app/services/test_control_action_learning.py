from __future__ import annotations

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
from app.services.control_action_learning import control_action_learning_service


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

    def _insert_metrics(self, *, apply_at: datetime, enough: bool = True) -> None:
        before_count = 20 if enough else 2
        after_count = 20 if enough else 3
        for i in range(before_count):
            ts = apply_at - timedelta(minutes=15) + timedelta(seconds=i * 40)
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
            ts = apply_at + timedelta(seconds=i * 40)
            temp = 36.9 + 0.005 * i
            err = temp - 37.0
            self.db.add(
                DeviceMetric(
                    device_id=self.device.id,
                    timestamp=ts,
                    current_temp=temp,
                    target_temp=37.0,
                    error=err,
                    pwm_output=52.0,
                    status="active",
                    in_spec=abs(err) <= 0.5,
                    is_alarm=False,
                )
            )
        self.db.commit()

    def test_manual_action_creates_control_action_and_pending_job(self) -> None:
        apply_at = datetime.utcnow()
        action, job = control_action_learning_service.create_action_and_eval_job(
            db=self.db,
            device=self.device,
            source="manual_user",
            source_ref_id=None,
            action_type="pid_apply",
            initiated_by="operator1",
            applied_at=apply_at,
            before={"control_mode": "pid_control", "target_temp": 37.0, "kp": 2.2, "ki": 0.3, "kd": 0.1},
            after={"control_mode": "pid_control", "target_temp": 37.0, "kp": 2.5, "ki": 0.34, "kd": 0.12},
            context_snapshot={"from_test": True},
        )
        self.assertEqual(action.source, "manual_user")
        self.assertEqual(action.status, "pending_eval")
        self.assertEqual(job.status, "pending")
        self.assertEqual(job.control_action_id, action.id)

    def test_ai_action_creates_control_action_and_pending_job(self) -> None:
        rec = AIRecommendation(
            device_id=self.device.id,
            reason="slow_response; effect=speed_up_response",
            suggestion="Kp:+0.2 Ki:+0.05 Kd:0",
            confidence=0.8,
            risk="Medium; requires_confirmation=True",
            last_run_at=datetime.utcnow(),
        )
        self.db.add(rec)
        self.db.commit()
        self.db.refresh(rec)

        action, job = control_action_learning_service.create_action_and_eval_job(
            db=self.db,
            device=self.device,
            source="ai_recommendation",
            source_ref_id=rec.id,
            action_type="pid_apply",
            initiated_by="operator1",
            applied_at=datetime.utcnow(),
            before={"control_mode": "pid_control", "target_temp": 37.0, "kp": 2.2, "ki": 0.3, "kd": 0.1},
            after={"control_mode": "pid_control", "target_temp": 37.0, "kp": 2.0, "ki": 0.28, "kd": 0.1},
            context_snapshot={"from_test": True},
        )
        self.assertEqual(action.source, "ai_recommendation")
        self.assertEqual(action.source_ref_id, rec.id)
        self.assertEqual(job.status, "pending")

    def test_evaluation_persists_feedback_sample_and_is_idempotent(self) -> None:
        apply_at = datetime.utcnow() - timedelta(minutes=12)
        action, _job = control_action_learning_service.create_action_and_eval_job(
            db=self.db,
            device=self.device,
            source="manual_user",
            source_ref_id=None,
            action_type="pid_apply",
            initiated_by="operator1",
            applied_at=apply_at,
            before={"control_mode": "pid_control", "target_temp": 37.0, "kp": 2.2, "ki": 0.3, "kd": 0.1},
            after={"control_mode": "pid_control", "target_temp": 37.0, "kp": 2.4, "ki": 0.34, "kd": 0.12},
        )
        self._insert_metrics(apply_at=apply_at, enough=True)

        first = control_action_learning_service.evaluate_control_action(
            db=self.db,
            control_action=action,
            observation_window_minutes=10,
            now_dt=datetime.utcnow(),
        )
        self.assertEqual(first.status, "done")
        self.assertIsNotNone(first.sample_id)

        second = control_action_learning_service.evaluate_control_action(
            db=self.db,
            control_action=action,
            observation_window_minutes=10,
            now_dt=datetime.utcnow(),
        )
        self.assertEqual(second.status, "done")
        rows = self.db.scalars(
            select(ControlActionFeedbackSample).where(ControlActionFeedbackSample.control_action_id == action.id)
        ).all()
        self.assertEqual(len(rows), 1)

    def test_insufficient_data_is_marked(self) -> None:
        apply_at = datetime.utcnow() - timedelta(minutes=2)
        action, _job = control_action_learning_service.create_action_and_eval_job(
            db=self.db,
            device=self.device,
            source="manual_user",
            source_ref_id=None,
            action_type="pid_apply",
            initiated_by="operator1",
            applied_at=apply_at,
            before={"control_mode": "pid_control", "target_temp": 37.0, "kp": 2.2, "ki": 0.3, "kd": 0.1},
            after={"control_mode": "pid_control", "target_temp": 37.0, "kp": 2.4, "ki": 0.34, "kd": 0.12},
        )
        self._insert_metrics(apply_at=apply_at, enough=False)
        result = control_action_learning_service.evaluate_control_action(
            db=self.db,
            control_action=action,
            observation_window_minutes=10,
            now_dt=datetime.utcnow(),
        )
        self.assertEqual(result.status, "insufficient_data")


if __name__ == "__main__":
    unittest.main()
