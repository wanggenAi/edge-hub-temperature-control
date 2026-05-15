#!/usr/bin/env python3
"""Generate reproducible control-validation metrics for the thesis.

The calculation mirrors the simulator-side first-order thermal model and
controller equations used by the edge firmware. It is intentionally offline:
the purpose is to produce repeatable engineering evidence for comparing control
variants before physical PCB validation.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


OUT_DIR = Path(__file__).resolve().parent
CSV_PATH = OUT_DIR / "control_validation_metrics.csv"
MD_PATH = OUT_DIR / "control_validation_metrics.md"


@dataclass(frozen=True)
class Variant:
    version: str
    method: str
    control_mode: str
    kp: float
    ki: float
    kd: float
    anti_windup: bool


@dataclass(frozen=True)
class Sample:
    second: int
    temperature_c: float
    error_c: float
    pwm_duty: float
    integral_error: float


@dataclass(frozen=True)
class Metrics:
    final_temp_c: float
    steady_state_abs_error_c: float
    max_overshoot_c: float
    settling_time_05_s: int | None
    settling_time_02_s: int | None
    mean_abs_error_c: float
    in_band_ratio_05_percent: float
    saturation_ratio_percent: float


TARGET_TEMP_C = 35.0
INITIAL_TEMP_C = 24.0
AMBIENT_TEMP_C = 22.0
HEAT_GAIN_PER_CYCLE_C = 1.60
COOLING_FACTOR = 0.08
MAX_DUTY = 255.0
INTEGRAL_MIN = -20.0
INTEGRAL_MAX = 20.0
CONTROL_PERIOD_S = 1.0
SIM_SECONDS = 900
STEADY_WINDOW_S = 60


VARIANTS = [
    Variant("V2", "P control", "p_control", 120.0, 0.0, 0.0, True),
    Variant("V3", "PI control, initial tuning", "pi_control", 120.0, 20.0, 0.0, False),
    Variant("V3.1", "PI control with anti-windup", "pi_control", 120.0, 12.0, 0.0, True),
]


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def simulate(variant: Variant) -> list[Sample]:
    temp = INITIAL_TEMP_C
    integral_error = 0.0
    samples: list[Sample] = []

    for second in range(SIM_SECONDS + 1):
        error = TARGET_TEMP_C - temp
        active_ki = 0.0 if variant.control_mode == "p_control" else variant.ki

        candidate_integral = clamp(
            integral_error + error * CONTROL_PERIOD_S,
            INTEGRAL_MIN,
            INTEGRAL_MAX,
        )
        candidate_output = error * variant.kp + candidate_integral * active_ki
        saturating_high = candidate_output > MAX_DUTY and error > 0.0
        saturating_low = candidate_output < 0.0 and error < 0.0

        if not variant.anti_windup or not (saturating_high or saturating_low):
            integral_error = candidate_integral

        raw_output = error * variant.kp + integral_error * active_ki
        pwm_duty = clamp(raw_output, 0.0, MAX_DUTY)
        samples.append(
            Sample(
                second=second,
                temperature_c=temp,
                error_c=error,
                pwm_duty=pwm_duty,
                integral_error=integral_error,
            )
        )

        pwm_norm = pwm_duty / MAX_DUTY
        heating = HEAT_GAIN_PER_CYCLE_C * pwm_norm
        cooling = COOLING_FACTOR * (temp - AMBIENT_TEMP_C)
        temp = temp + heating - cooling

    return samples


def settling_time(samples: list[Sample], threshold_c: float) -> int | None:
    errors = [abs(sample.error_c) for sample in samples]
    for index, sample in enumerate(samples):
        if all(error <= threshold_c for error in errors[index:]):
            return sample.second
    return None


def calculate_metrics(samples: list[Sample]) -> Metrics:
    temps = [sample.temperature_c for sample in samples]
    abs_errors = [abs(sample.error_c) for sample in samples]
    steady_samples = samples[-STEADY_WINDOW_S:]
    steady_abs_errors = [abs(sample.error_c) for sample in steady_samples]
    steady_temps = [sample.temperature_c for sample in steady_samples]

    return Metrics(
        final_temp_c=sum(steady_temps) / len(steady_temps),
        steady_state_abs_error_c=sum(steady_abs_errors) / len(steady_abs_errors),
        max_overshoot_c=max(0.0, max(temps) - TARGET_TEMP_C),
        settling_time_05_s=settling_time(samples, 0.5),
        settling_time_02_s=settling_time(samples, 0.2),
        mean_abs_error_c=sum(abs_errors) / len(abs_errors),
        in_band_ratio_05_percent=sum(1 for error in abs_errors if error <= 0.5) / len(abs_errors) * 100.0,
        saturation_ratio_percent=sum(1 for sample in samples if sample.pwm_duty <= 0.5 or sample.pwm_duty >= 254.5)
        / len(samples)
        * 100.0,
    )


def format_time(value: int | None) -> str:
    return "not reached" if value is None else str(value)


def write_outputs(results: list[tuple[Variant, Metrics]]) -> None:
    with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "version",
                "method",
                "kp",
                "ki",
                "kd",
                "anti_windup",
                "final_temp_c",
                "steady_state_abs_error_c",
                "max_overshoot_c",
                "settling_time_05_s",
                "settling_time_02_s",
                "mean_abs_error_c",
                "in_band_ratio_05_percent",
                "saturation_ratio_percent",
            ]
        )
        for variant, metrics in results:
            writer.writerow(
                [
                    variant.version,
                    variant.method,
                    f"{variant.kp:.1f}",
                    f"{variant.ki:.1f}",
                    f"{variant.kd:.1f}",
                    str(variant.anti_windup).lower(),
                    f"{metrics.final_temp_c:.3f}",
                    f"{metrics.steady_state_abs_error_c:.3f}",
                    f"{metrics.max_overshoot_c:.3f}",
                    format_time(metrics.settling_time_05_s),
                    format_time(metrics.settling_time_02_s),
                    f"{metrics.mean_abs_error_c:.3f}",
                    f"{metrics.in_band_ratio_05_percent:.1f}",
                    f"{metrics.saturation_ratio_percent:.1f}",
                ]
            )

    lines = [
        "# Control Validation Metrics",
        "",
        "This file is generated by `experiments/control_validation_metrics.py`.",
        "",
        "The offline experiment mirrors the edge simulator's first-order thermal model and controller equations.",
        f"The target temperature is {TARGET_TEMP_C:.1f} C, the initial simulated temperature is {INITIAL_TEMP_C:.1f} C, "
        f"the control period is {CONTROL_PERIOD_S:.0f} s, and each run lasts {SIM_SECONDS} s.",
        "",
        "| Version | Method | Kp | Ki | Anti-windup | Final temp, C | Steady-state abs. error, C | Max overshoot, C | Settling time within 0.5 C, s | Settling time within 0.2 C, s | Mean abs. error, C | In-band ratio within 0.5 C, % | Saturation ratio, % |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for variant, metrics in results:
        lines.append(
            "| "
            f"{variant.version} | {variant.method} | {variant.kp:.1f} | {variant.ki:.1f} | "
            f"{'yes' if variant.anti_windup else 'no'} | {metrics.final_temp_c:.3f} | "
            f"{metrics.steady_state_abs_error_c:.3f} | {metrics.max_overshoot_c:.3f} | "
            f"{format_time(metrics.settling_time_05_s)} | {format_time(metrics.settling_time_02_s)} | "
            f"{metrics.mean_abs_error_c:.3f} | {metrics.in_band_ratio_05_percent:.1f} | "
            f"{metrics.saturation_ratio_percent:.1f} |"
        )
    lines.extend(
        [
            "",
            "Interpretation:",
            "",
            "- V2 verifies the closed-loop path but leaves a visible steady-state error.",
            "- V3 removes steady-state error but introduces a transient overshoot.",
            "- V3.1 preserves the final accuracy while removing the overshoot in this simulator profile.",
        ]
    )
    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    results = [(variant, calculate_metrics(simulate(variant))) for variant in VARIANTS]
    write_outputs(results)
    print(f"Wrote {CSV_PATH}")
    print(f"Wrote {MD_PATH}")


if __name__ == "__main__":
    main()
