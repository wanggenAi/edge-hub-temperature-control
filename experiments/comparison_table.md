# Control Version Comparison Table

## 1. Comparison Scope

This table summarizes the current staged control experiments of the Wokwi-based temperature-control node. It is intended to support follow-up tuning work, experiment traceability, and later thesis writing.

## 2. Comparison Table

| Version | Control Method | Closed Loop Formed | Steady-State Error | Overshoot | Convergence Speed | Current Assessment |
| --- | --- | --- | --- | --- | --- | --- |
| V2 | P control | Yes | Yes, visible | No obvious overshoot | Fast initial approach | Suitable for verifying the basic closed-loop architecture |
| V3 | PI control, initial version | Yes | Greatly reduced | Yes, mild | Fast, but less smooth near the target | Suitable for showing the benefit of integral action |
| V3.1 | PI control, tuned version | Yes | Very small | Reduced compared with V3 | Moderate and smoother | Most suitable current-stage demonstration version |

## 3. Brief Notes

- V2 is important because it clearly shows the steady-state error problem of proportional control.
- V3 is important because it demonstrates that adding integral action can greatly improve final accuracy.
- V3.1 is currently the best compromise between clarity, smoothness, and target tracking performance.

## 4. Recommended Follow-Up Metrics

For the next stage, the following indicators are recommended for more formal comparison:

- settling time
- maximum overshoot
- steady-state error
- final PWM duty cycle
- integral state evolution
