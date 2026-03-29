# P Control Experiment Record V2

## 1. Experiment Objective

The objective of this experiment was to verify that the edge-node simulation could form a basic closed-loop temperature-control process after the introduction of a first-order virtual thermal model.

This stage focused on validating the engineering chain from control computation to PWM output and thermal-state feedback, rather than on achieving the best possible regulation accuracy.

## 2. Control Method

- Version: V2
- Controller type: proportional control
- Controlled variable: `sim_temp_c`
- Reference target: 35.0 C
- Control period: 1 s
- Actuator output: PWM duty cycle on GPIO18
- Thermal process model: first-order heating and cooling model

## 3. Key Parameters

At this stage, the controller used proportional-only regulation. The current document mainly records the observed behavior and engineering meaning of this stage rather than a full parameter table for later tuning work.

Known experimental conditions:

- target temperature: 35.0 C
- ambient temperature: 22.0 C
- initial simulated temperature: lower than the target
- output clamp: 0 to 255

## 4. Key Observations

- The system formed a clear closed loop after the thermal model was introduced.
- The simulated temperature increased steadily from the initial state.
- The PWM duty cycle started at a relatively high level and then decreased as the error became smaller.
- The overall response was easy to observe and explain.
- The regulated temperature remained slightly below the target temperature after the transient process ended.

Typical steady behavior:

- target temperature: 35.0 C
- final regulated temperature: approximately 34.13 to 34.14 C

## 5. Result Analysis

This result is consistent with the known behavior of proportional control. As the process variable approaches the target, the error becomes smaller, and the output effort also decreases. Because a certain amount of heating power is still needed to balance thermal loss, the system stabilizes with a nonzero error.

From an experiment-design perspective, this stage was valuable because it made the steady-state error visible in a controlled and explainable way. That provided a clear motivation for introducing the integral term in the next stage.

## 6. Stage Conclusion

V2 completed the first meaningful closed-loop verification of the current edge-node simulation. It showed that the system architecture, PWM output, virtual thermal model, and serial logging already support closed-loop control experiments.

However, the experiment also confirmed that proportional control alone was not sufficient to eliminate steady-state error in the current temperature-control scenario.
