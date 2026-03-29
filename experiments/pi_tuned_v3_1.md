# Tuned PI Control Experiment Record V3.1

## 1. Experiment Objective

The objective of this experiment was to improve the transient response of the initial PI controller, reduce overshoot, and obtain a more balanced closed-loop behavior while keeping the implementation simple and explainable.

## 2. Control Method

- Version: V3.1
- Controller type: tuned PI control
- Controlled variable: `sim_temp_c`
- Reference target: 35.0 C
- Control period: 1 s
- Actuator output: PWM duty cycle on GPIO18
- Thermal process model: first-order heating and cooling model
- Additional mechanism: simple anti-windup

## 3. Key Parameters

Current known controller settings:

- `Kp = 120.0`
- `Ki = 12.0`
- integral lower limit: `-20.0`
- integral upper limit: `20.0`

Simple anti-windup strategy:

- when the output is already saturated and the current error would push the output further into the same saturation direction, pause integral accumulation for that cycle

## 4. Key Observations

- Overshoot was reduced compared with V3.
- The convergence process became smoother.
- The final temperature stabilized very close to the target.
- The typical final regulated temperature was approximately 34.99 to 35.00 C.
- The controller remained sufficiently simple for undergraduate engineering explanation and staged experimental analysis.

## 5. Result Analysis

The tuned PI controller retained the benefit of integral action, namely the ability to greatly reduce the steady-state error, but introduced a more careful treatment of the integral state. By avoiding unnecessary accumulation during saturation, the controller reduced part of the excess stored integral action that had contributed to overshoot in the previous version.

This stage did not attempt to build a full industrial PID controller. Instead, it focused on achieving a better balance between clarity, controllability, and experimental usefulness.

## 6. Stage Conclusion

V3.1 is the best current-stage demonstration version among the completed control variants. It offers a near-target final temperature, reduced overshoot, and a smoother overall closed-loop behavior while preserving a simple implementation structure.
