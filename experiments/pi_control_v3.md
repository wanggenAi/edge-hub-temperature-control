# PI Control Experiment Record V3

## 1. Experiment Objective

The objective of this experiment was to reduce the steady-state error observed in V2 by adding an integral term to the controller while keeping the control logic simple enough for simulation analysis and thesis description.

## 2. Control Method

- Version: V3
- Controller type: PI control
- Controlled variable: `sim_temp_c`
- Reference target: 35.0 C
- Control period: 1 s
- Actuator output: PWM duty cycle on GPIO18
- Thermal process model: first-order heating and cooling model

## 3. Key Parameters

At this stage, the controller introduced:

- proportional action
- integral action
- bounded integral state
- output clamp from 0 to 255

The main purpose of this version was to observe the effect of integral action on steady-state error and transient behavior.

## 4. Key Observations

- The final temperature moved much closer to the target than in V2.
- The steady-state error was reduced significantly.
- The regulated temperature could exceed 35.0 C during the transient process.
- A mild overshoot appeared, with a typical peak of about 35.23 C.
- The integral state accumulated quickly in the early stage and took longer to decay afterward.

## 5. Result Analysis

The integral term improved the controller’s ability to remove the offset left by proportional control. This made the final regulated temperature much more accurate than in V2.

At the same time, the experiment showed a new issue: because the integral term accumulated rapidly while the error was still large, the system retained more control effort than necessary near the target. This led to mild overshoot and a less balanced transient response.

This stage therefore confirmed both the benefit and the tuning challenge of PI control.

## 6. Stage Conclusion

V3 successfully demonstrated that PI control is effective in reducing steady-state error in the current simulation framework. It also provided the practical motivation for a follow-up tuning stage focused on overshoot reduction and smoother convergence.
