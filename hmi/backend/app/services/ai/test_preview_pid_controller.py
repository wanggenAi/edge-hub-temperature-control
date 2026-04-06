from __future__ import annotations

import unittest

from app.services.ai.preview_simulator import (
    PreviewPidController,
    PreviewSimulationConfig,
    RecommendationPreviewSimulator,
)
from app.services.ai.schemas import PIDParams


class PreviewPidControllerModeTests(unittest.TestCase):
    def test_pid_controller_golden_sequence_snapshot(self) -> None:
        """Golden-case snapshot to keep Python preview PID aligned with device-side behavior."""
        controller = PreviewPidController()
        cfg = PreviewSimulationConfig(
            max_duty=100.0,
            integral_min=-20.0,
            integral_max=20.0,
            derivative_filter_alpha=0.2,
            control_mode="pid_control",
        )
        params = PIDParams(kp=2.0, ki=0.5, kd=1.2)

        sequence = [
            (37.0, 30.0, 1.0),
            (37.0, 31.5, 1.0),
            (37.0, 33.4, 1.0),
            (37.0, 35.8, 1.0),
            (37.0, 36.6, 1.0),
            (37.0, 37.4, 1.0),
        ]
        expected = [
            {"error": 7.0, "derivative_error": 0.0, "d_term": 0.0, "integral_error": 7.0, "raw_output": 17.5, "control_output": 17.5, "saturation_state": "none"},
            {"error": 5.5, "derivative_error": -0.3, "d_term": -0.36, "integral_error": 12.5, "raw_output": 16.89, "control_output": 16.89, "saturation_state": "none"},
            {"error": 3.6, "derivative_error": -0.62, "d_term": -0.744, "integral_error": 16.1, "raw_output": 14.506, "control_output": 14.506, "saturation_state": "none"},
            {"error": 1.2, "derivative_error": -0.976, "d_term": -1.1712, "integral_error": 17.3, "raw_output": 9.8788, "control_output": 9.8788, "saturation_state": "none"},
            {"error": 0.4, "derivative_error": -0.9408, "d_term": -1.12896, "integral_error": 17.7, "raw_output": 8.52104, "control_output": 8.52104, "saturation_state": "none"},
            {"error": -0.4, "derivative_error": -0.91264, "d_term": -1.095168, "integral_error": 17.3, "raw_output": 6.754832, "control_output": 6.754832, "saturation_state": "none"},
        ]

        for i, (target, measured, dt_s) in enumerate(sequence):
            out = controller.update(target_temp=target, measured_temp=measured, dt_s=dt_s, params=params, config=cfg)
            exp = expected[i]
            self.assertAlmostEqual(out.error, exp["error"], places=6)
            self.assertAlmostEqual(out.derivative_error, exp["derivative_error"], places=6)
            self.assertAlmostEqual(out.d_term, exp["d_term"], places=6)
            self.assertAlmostEqual(out.integral_error, exp["integral_error"], places=6)
            self.assertAlmostEqual(out.raw_output, exp["raw_output"], places=6)
            self.assertAlmostEqual(out.control_output, exp["control_output"], places=6)
            self.assertEqual(out.saturation_state, exp["saturation_state"])

    def test_pid_controller_golden_anti_windup_high_saturation(self) -> None:
        controller = PreviewPidController()
        cfg = PreviewSimulationConfig(
            max_duty=20.0,
            integral_min=-10.0,
            integral_max=10.0,
            derivative_filter_alpha=0.2,
            control_mode="pid_control",
        )
        params = PIDParams(kp=30.0, ki=2.0, kd=0.0)
        sequence = [
            (37.0, 30.0, 1.0),
            (37.0, 31.0, 1.0),
            (37.0, 34.0, 1.0),
            (37.0, 36.5, 1.0),
        ]
        expected = [
            {"integral_error": 0.0, "raw_output": 210.0, "control_output": 20.0, "saturation_state": "high"},
            {"integral_error": 0.0, "raw_output": 180.0, "control_output": 20.0, "saturation_state": "high"},
            {"integral_error": 0.0, "raw_output": 90.0, "control_output": 20.0, "saturation_state": "high"},
            {"integral_error": 0.5, "raw_output": 16.0, "control_output": 16.0, "saturation_state": "none"},
        ]
        for i, (target, measured, dt_s) in enumerate(sequence):
            out = controller.update(target_temp=target, measured_temp=measured, dt_s=dt_s, params=params, config=cfg)
            exp = expected[i]
            self.assertAlmostEqual(out.integral_error, exp["integral_error"], places=6)
            self.assertAlmostEqual(out.raw_output, exp["raw_output"], places=6)
            self.assertAlmostEqual(out.control_output, exp["control_output"], places=6)
            self.assertEqual(out.saturation_state, exp["saturation_state"])

    def test_derivative_filter_matches_device_sequence(self) -> None:
        controller = PreviewPidController()
        cfg = PreviewSimulationConfig(
            max_duty=100.0,
            integral_min=-20.0,
            integral_max=20.0,
            derivative_filter_alpha=0.2,
            control_mode="pid_control",
        )
        params = PIDParams(kp=1.0, ki=0.0, kd=1.0)

        # first update: previous_error_initialized = False => derivative should be 0
        first = controller.update(target_temp=10.0, measured_temp=0.0, dt_s=1.0, params=params, config=cfg)
        self.assertAlmostEqual(first.derivative_error, 0.0, places=6)
        self.assertAlmostEqual(first.d_term, 0.0, places=6)

        # second update: raw_derivative = (8 - 10) / 1 = -2
        # filtered = 0.2 * -2 + 0.8 * 0 = -0.4
        second = controller.update(target_temp=10.0, measured_temp=2.0, dt_s=1.0, params=params, config=cfg)
        self.assertAlmostEqual(second.derivative_error, -0.4, places=6)
        self.assertAlmostEqual(second.d_term, -0.4, places=6)

    def test_anti_windup_blocks_integral_when_saturating_high(self) -> None:
        controller = PreviewPidController()
        cfg = PreviewSimulationConfig(
            max_duty=10.0,
            integral_min=-50.0,
            integral_max=50.0,
            derivative_filter_alpha=0.2,
            control_mode="pid_control",
        )
        params = PIDParams(kp=100.0, ki=1.0, kd=0.0)

        out = controller.update(target_temp=10.0, measured_temp=0.0, dt_s=1.0, params=params, config=cfg)
        self.assertAlmostEqual(out.integral_error, 0.0, places=6)
        self.assertEqual(out.saturation_state, "high")
        self.assertAlmostEqual(out.control_output, 10.0, places=6)

    def test_anti_windup_blocks_integral_when_saturating_low(self) -> None:
        controller = PreviewPidController()
        cfg = PreviewSimulationConfig(
            max_duty=100.0,
            integral_min=-50.0,
            integral_max=50.0,
            derivative_filter_alpha=0.2,
            control_mode="pid_control",
        )
        params = PIDParams(kp=20.0, ki=1.0, kd=0.0)

        out = controller.update(target_temp=0.0, measured_temp=10.0, dt_s=1.0, params=params, config=cfg)
        self.assertAlmostEqual(out.integral_error, 0.0, places=6)
        self.assertEqual(out.saturation_state, "low")
        self.assertAlmostEqual(out.control_output, 0.0, places=6)

    def test_p_control_disables_ki_kd(self) -> None:
        controller = PreviewPidController()
        cfg = PreviewSimulationConfig(
            max_duty=100.0,
            integral_min=-100.0,
            integral_max=100.0,
            derivative_filter_alpha=0.2,
            control_mode="p_control",
        )
        params = PIDParams(kp=2.0, ki=5.0, kd=7.0)

        first = controller.update(target_temp=10.0, measured_temp=0.0, dt_s=1.0, params=params, config=cfg)
        second = controller.update(target_temp=10.0, measured_temp=3.0, dt_s=1.0, params=params, config=cfg)

        expected_first = max(0.0, min(cfg.max_duty, params.kp * (10.0 - 0.0)))
        expected_second = max(0.0, min(cfg.max_duty, params.kp * (10.0 - 3.0)))
        self.assertAlmostEqual(first.control_output, expected_first, places=6)
        self.assertAlmostEqual(second.control_output, expected_second, places=6)
        self.assertAlmostEqual(first.d_term, 0.0, places=6)
        self.assertAlmostEqual(second.d_term, 0.0, places=6)

    def test_simulator_respects_control_mode(self) -> None:
        sim = RecommendationPreviewSimulator()
        params = PIDParams(kp=1.2, ki=0.5, kd=0.2)

        pid_out = sim.run(
            current_temp=31.0,
            target_temp=37.0,
            baseline_params=params,
            recommended_params=params,
            config=PreviewSimulationConfig(
                horizon_sec=180,
                step_sec=1,
                control_mode="pid_control",
            ),
        )
        p_out = sim.run(
            current_temp=31.0,
            target_temp=37.0,
            baseline_params=params,
            recommended_params=params,
            config=PreviewSimulationConfig(
                horizon_sec=180,
                step_sec=1,
                control_mode="p_control",
            ),
        )

        # With same Kp/Ki/Kd inputs, disabling Ki/Kd in p_control should produce a different trajectory.
        self.assertNotEqual(
            round(pid_out.baseline_curve[-1].temp, 4),
            round(p_out.baseline_curve[-1].temp, 4),
        )


if __name__ == "__main__":
    unittest.main()
