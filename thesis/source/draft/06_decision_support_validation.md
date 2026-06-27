# 5 AUXILIARY DECISION-SUPPORT AND SYSTEM VALIDATION

## 5.1 Purpose of decision support

The purpose of the auxiliary decision-support mechanism is to help the operator interpret stored control behavior and prepare reviewable parameter recommendations. It is not the main controller of the developed system. Local measurement, control calculation, and actuator output remain in the edge control layer, while the Data Hub and HMI provide the supervisory and data-processing environment around this local loop.

In the developed system, decision support is connected to historical telemetry, parameter records, acknowledgement records, and HMI actions. Its input is therefore not an isolated temperature value, but a window of engineering context that describes how the controlled process behaved before and after a parameter change. The mechanism analyzes this context and produces a recommendation that can be reviewed by the operator. If the recommendation is accepted, it is applied through the same HMI and MQTT command path as a manual parameter update.

This boundary is important for safety and explainability. The mechanism can identify possible slow response, steady-state error, overshoot, oscillation, or saturation-limited behavior, but it does not directly write to the actuator and does not bypass acknowledgement. The operator remains responsible for applying the change and checking subsequent measurements. The auxiliary mechanism therefore supports the layered closed-loop workflow instead of replacing it.

## 5.2 Data preparation and feature extraction

The decision-support mechanism requires prepared data rather than raw messages alone. Telemetry records are first collected by the edge node, delivered through MQTT, parsed by the Data Hub, and stored with timestamps, setpoints, measured or simulated temperature values, controller output, PWM duty, saturation state, controller parameters, and device status. This stored history makes it possible to calculate behavior indicators over a defined observation window.

The main extracted indicators are selected to match control-engineering meaning. Mean error and mean absolute error describe the deviation from the setpoint. Error standard deviation and temperature swing describe oscillation or unstable behavior. In-band ratio describes how much of the observation window remains inside the accepted target band. Overshoot describes how far the process exceeds the target. Settling time describes how long the response takes to remain inside the target band. Saturation ratio describes how often the actuator output reaches the configured limit. The indicators used in the developed mechanism are summarized in Table 5.1.

The feature-extraction implementation is shown in Figure 5.1. It calculates the indicators from a telemetry window and returns them as a structured feature set. This design keeps the recommendation mechanism explainable: each later decision can be traced to measurable control-behavior features rather than to an opaque screen action.

Table 5.1 – Main control-behavior indicators used for decision support

| Indicator | Calculation basis | Engineering meaning |
| --- | --- | --- |
| Mean absolute error | Absolute value of temperature error over the observation window | General tracking quality |
| In-band ratio | Share of samples inside the target band | Stability around the setpoint |
| Overshoot | Maximum temperature excess above target | Risk of excessive heating |
| Settling time | First time after which the error remains inside the target band | Speed of response |
| Temperature swing | Difference between maximum and minimum temperature in the window | Oscillation or instability |
| Saturation ratio | Share of samples at or above the PWM saturation threshold | Limited actuator headroom |

## 5.3 Recommendation and feedback mechanism

The recommendation logic uses the extracted indicators to classify the observed behavior and select a limited parameter change. This is intentionally conservative. The mechanism should not produce large uncontrolled jumps in controller coefficients, because the physical temperature process has inertia and a delayed response. A recommendation must therefore be small enough to review and test through post-apply observation.

The classification step uses rule thresholds for behavior patterns. For example, frequent zero crossings together with high error spread indicate oscillation, high overshoot indicates an excessive transient response, and high saturation ratio indicates that the actuator has limited remaining authority. Slow response is detected when the mean absolute error remains high and the response does not settle within the expected time. These rules are simple, but they are transparent and can be checked against stored data.

The rule-based recommendation fragment is shown in Figure 5.2. It changes PID coefficients according to the detected problem type and limits the change step. For slow response it increases proportional and integral influence moderately. For steady-state error it mainly increases the integral term. For overshoot or oscillation it reduces aggressive terms and can increase derivative damping. For saturation-limited behavior it treats the recommendation as higher risk. In all non-normal cases, explicit operator confirmation is required.

The feedback mechanism closes the recommendation path. After a recommendation is applied through the HMI, the edge device must acknowledge the parameter update. Later telemetry is then compared with the pre-apply behavior and with the predicted preview. This prevents the system from treating a recommendation as successful merely because a message was published.

## 5.4 Experimental setup

The validation was organized as a staged engineering check of the implemented closed-loop platform. The purpose was not to claim final industrial hardware certification, but to verify that the implemented layers work together: edge telemetry generation, MQTT exchange, Data Hub ingestion, storage, HMI monitoring, parameter command publication, device acknowledgement, decision-support preparation, and post-apply observation [2].

The main test environment used the ESP32-oriented edge firmware structure with the Wokwi/simulator profile, the Data Hub ingestion service, persistent storage, and the HMI frontend [11]. The simulator profile was used because the physical PCB and enclosure have been designed but not yet electrically and thermally tested as assembled hardware. This boundary is important: the validation confirms the software and system workflow, while final physical circuit validation must later be performed with instruments such as an oscilloscope, multimeter, external thermometer, and controlled load.

The validation scenarios are summarized in Table 5.2. They cover the main system behavior expected from a layered closed-loop temperature-control and monitoring system.

Table 5.2 – Validation scenarios for the developed system

| Scenario | Checked path | Expected result |
| --- | --- | --- |
| Telemetry ingestion | Edge telemetry → MQTT → Data Hub parsing → storage | Structured records are stored with device, setpoint, output, and status context |
| HMI monitoring | Stored telemetry → backend API → frontend screen | Current state and historical behavior are visible to the operator |
| Parameter update | HMI request → backend command path → MQTT params/set | Command is sent through the upper-layer command path |
| Acknowledgement | Edge validation → MQTT params/ack → Data Hub storage → HMI feedback | Operator can distinguish requested, rejected, staged, and applied commands |
| Decision support | Stored history → feature extraction → recommendation generation | Recommendation is explainable and requires review |
| Post-apply verification | Applied parameters → later telemetry → before/after comparison | Actual behavior is compared with baseline and preview |

## 5.5 Closed-loop tests

Closed-loop testing focused on whether the system preserves the engineering meaning of each action. A temperature sample should not disappear as an isolated screen value; it should become a stored telemetry fact. A parameter command should not be treated as successful until the device acknowledges it. A recommendation should not be treated as final until later behavior is observed.

The first group of tests verified telemetry continuity. The edge node generated periodic telemetry that included the target temperature, current process value, control error, controller output, PWM duty, saturation state, and controller parameters. The Data Hub ingested these records and stored them for later use by the HMI and decision-support mechanism. This confirmed the measurement-to-storage part of the loop.

The second group of tests verified parameter command handling. A new setpoint or controller parameter set was submitted through the HMI. The backend published the command through the configured MQTT path, and the edge device parsed and validated the payload. If the payload was accepted, the device returned an acknowledgement with the active runtime parameters. If the payload was invalid, the acknowledgement contained a failure result and a reason. This confirmed that the operator action was not reduced to a simple frontend event.

The third group of tests verified post-apply observation. After a parameter update, later telemetry was compared with the pre-apply baseline. The HMI validation view shown in Figure 5.3 presents the baseline, preview, and actual behavior around the application moment. This screenshot demonstrates the intended interpretation of decision support: the recommendation is useful only if the actual response after application can be observed and compared.

## 5.6 Telemetry and HMI validation

The HMI validation screen provides visual evidence of the post-apply verification workflow. In the shown validation case, the HMI compares the baseline behavior before the recommendation, the preview behavior prepared before application, and the actual behavior after application. The visualization also displays summary indicators such as in-band ratio, overshoot, settling time, mean absolute error, saturation ratio, and temperature swing.

The post-apply evaluator implementation is shown in Figure 5.4. It calculates actual metrics from observed telemetry points and compares them with a reference. The comparison is direction-aware: a higher in-band ratio is treated as improvement, while lower overshoot, lower mean absolute error, lower saturation ratio, lower temperature swing, and shorter settling time are treated as improvement. This makes the validation result more meaningful than a simple statement that the command was applied.

The main result values visible in the HMI validation scenario are summarized in Table 5.3. These values are used as demonstration evidence for the software workflow and should be interpreted as simulated or seeded validation data, not as final measurements of the untested physical PCB.

Table 5.3 – Example post-apply validation result from the HMI scenario

| Indicator | Before application | After application | Result |
| --- | --- | --- | --- |
| In-band ratio | 36.7 % | 84.4 % | Improved |
| Overshoot | 2.339 °C | 0.788 °C | Improved |
| Settling time | 5160 s | 2100 s | Improved |
| Mean absolute error | 1.079 °C | 0.246 °C | Improved |
| Saturation ratio | 46.7 % | 0.0 % | Improved |
| Temperature swing | 2.635 °C | 0.922 °C | Improved |

The result shows that the tested validation scenario successfully demonstrates the post-apply comparison path. The most important conclusion is not that the chosen parameters are universally optimal, but that the system can preserve enough information to evaluate whether a parameter change improved the observed behavior.

## 5.7 Results analysis

The validation confirms that the developed system implements the intended layered closed-loop workflow. The edge layer produces control-related telemetry and acknowledgements. The Data Hub parses and stores the records. The HMI provides monitoring, parameter configuration, command feedback, and post-apply observation. The auxiliary decision-support mechanism uses stored behavior to prepare reviewable recommendations and keeps the operator in the loop.

The experimental result also shows why persistent telemetry is necessary. Without stored baseline and post-apply windows, it would be impossible to distinguish a successful parameter change from a communication event that only appeared successful. The before/after metrics provide a clearer engineering basis for evaluation than the current temperature value alone.

At the same time, the result has clear limitations. The validation is based on the implemented software platform, simulator-oriented edge behavior, stored telemetry, and HMI demonstration data. The physical PCB, heater driver, sensor placement, and enclosure have not yet been fully verified under real electrical and thermal load. Therefore, the thesis should not claim final industrial readiness. The correct conclusion is that the developed prototype demonstrates a complete closed-loop engineering workflow and provides a foundation for later hardware deployment and instrument-based testing.

The chapter therefore completes the implementation evidence for the project. It connects decision support, HMI operation, command acknowledgement, and post-apply behavior analysis into one traceable validation process. The final section of the thesis summarizes the obtained result and defines the remaining work required before a real hardware installation.

The most important engineering result of the validation is the preservation of causality across layers. A recommendation is generated from stored behavior, reviewed by the operator, applied through the command path, acknowledged by the edge device, and then evaluated against later telemetry. Each stage leaves a record that can be inspected independently. This makes the prototype stronger than a simple dashboard because it supports explanation of both successful and unsuccessful parameter changes.

The validation also defines the next experimental step. After the PCB is fabricated and assembled, the same metrics should be repeated with instrument-supported measurements. In that stage, oscilloscope traces of PWM switching, measured heater current, regulator stability, external temperature readings, and sensor-placement checks should be compared with the stored telemetry. The software workflow developed in this thesis is prepared for that later test because it already stores the data needed to compare command intent, device acknowledgement, and observed thermal response.

For this reason, the validation chapter should be read as a bridge between software verification and future physical testing. It proves that the implemented platform can collect the required evidence, calculate meaningful control-quality indicators, and present the result to the operator. The remaining hardware stage will reuse the same procedure with real sensor and actuator measurements, which means that the thesis result is not limited to a visual demonstration but forms a reproducible validation method for the later assembled node.
