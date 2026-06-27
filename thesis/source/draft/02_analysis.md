# 1 ANALYSIS OF TEMPERATURE CONTROL AND MONITORING SYSTEMS

## 1.1 Temperature-control process characteristics

Temperature control is a common engineering task in heating units, laboratory equipment, environmental chambers, embedded automation systems, and industrial processes. The controlled variable is temperature, while the desired operating condition is defined by a setpoint. The purpose of the control system is to keep the measured temperature close to this setpoint despite internal process dynamics and external influences [1].

A temperature-control process has several characteristics that make it more complex than a simple measurement task. One of the main characteristics is thermal inertia. When the actuator output changes, the temperature of the controlled object does not change immediately. Heat is accumulated in the object, transferred through its material, and dissipated to the surrounding environment. As a result, the measured response appears with delay, and the controller must take into account that the effect of the current actuator signal will become visible only after some time.

Another important characteristic is the influence of disturbances. Ambient temperature changes, airflow, load variation, heat losses, sensor placement, and power-supply instability can affect the process. These disturbances may shift the temperature away from the setpoint even if the controller settings remain unchanged. Therefore, the system must be able to react to changing conditions and not rely only on a fixed actuator output.

Sensor noise and measurement uncertainty also affect temperature-control quality. A sensor may produce small fluctuations even when the physical temperature is nearly constant. If the controller reacts too strongly to such fluctuations, unnecessary actuator changes and oscillations may appear. At the same time, excessive filtering can make the control response slower. This creates a practical trade-off between measurement stability and control responsiveness.

Actuator limitations must also be considered. A heater, fan, relay, valve, or PWM-controlled output has a limited operating range and cannot produce an unlimited control effect. If the actuator reaches saturation, the system may not be able to reduce the control error quickly. Incorrect controller settings may lead to overshoot, when the temperature exceeds the setpoint, or to steady-state error, when the temperature remains below or above the required value for a long time. These characteristics show that temperature control requires not only measurement, but also stable control logic, parameter management, and observation of process behavior.

## 1.2 Closed-loop control principles

A closed-loop control system uses feedback from the controlled object to correct its own behavior. The basic control sequence includes measurement of the process value, comparison with the setpoint, calculation of the control action, application of this action to the actuator, and repeated observation of the result. This repeated correction allows the system to compensate for disturbances and process changes that cannot be fully predicted in advance.

In a temperature-control system, the measured temperature is periodically read from a sensor and compared with the required setpoint. The difference between these values is used to calculate the actuator output. If the temperature is lower than the setpoint, the controller may increase heating power. If the temperature is higher than required, the controller may reduce the output or switch the actuator off. The process is repeated continuously, so each new measurement becomes feedback for the next control decision.

Closed-loop control is more suitable for temperature regulation than open-loop control because the actual process response can change over time. The same actuator output may produce different temperature behavior depending on environmental conditions, thermal load, heat losses, and the current state of the object. Without feedback, the system cannot determine whether the expected result has been achieved. With feedback, the controller can adjust its output according to the measured response.

In the developed project, the closed-loop principle is extended beyond the local controller. The local loop remains responsible for measurement, control calculation, and actuator output. However, the complete engineering workflow also includes supervisory parameter changes and result verification. A parameter update is prepared in the HMI, published as an MQTT command, received by the edge device, acknowledged after processing, stored by the Data Hub, and then checked through subsequent process behavior. This extended loop is important because it connects operator action with device response and post-apply verification.

## 1.3 Edge-based execution in temperature-control systems

Edge-based execution means that the time-critical part of the control system is performed close to the controlled object. In a temperature-control system, this approach is important because measurement, control calculation, and actuator output must continue even if the HMI, database, or network connection is temporarily unavailable. The local controller must not depend on a remote service for every control decision.

The edge control layer is therefore responsible for direct interaction with the controlled process. It acquires temperature values, executes the local control algorithm, applies actuator output, maintains runtime parameters, publishes structured telemetry, receives parameter commands, and returns acknowledgements. These functions must be coordinated so that communication activity does not interrupt the local feedback process.

Keeping control execution at the edge also reduces the influence of communication delay. If every actuator update depended on a remote server, unstable network conditions could lead to delayed or missed control actions. In contrast, edge-based execution allows the device to continue operating with the last valid configuration while higher layers provide monitoring, storage, configuration, and analysis.

For the developed system, the edge control layer is the execution core of the closed-loop temperature control and monitoring system. It is not only a data source for the HMI, but also the component that applies control logic and confirms configuration changes. This role requires clear separation between local control responsibilities and supervisory functions implemented in the Data Hub and HMI layers.

## 1.4 Data acquisition and monitoring requirements

Data acquisition in a temperature-control system must provide structured and traceable information about the controlled process. The system should not collect only temperature values, because a single value does not explain the state of the controller or the reason for a change in behavior. For engineering analysis, each record should include context that allows the process state to be reconstructed.

The required context includes the device identifier, timestamp, measured temperature, setpoint, actuator output, controller state, command identifier, acknowledgement status, parameter version, and abnormal conditions. These fields make it possible to compare behavior before and after parameter changes, determine which configuration was active, and understand whether the edge device accepted a command.

MQTT is suitable for this type of system because it provides lightweight message exchange between the edge device and supervisory software [2]. Separate topics or message types can be used for structured telemetry, parameter commands, acknowledgements, and system events. This separation improves traceability and makes the communication flow easier to process and verify.

The Data Hub layer is responsible for ingestion and processing of these messages. It subscribes to MQTT topics, parses payloads into stable data models, filters or aggregates measurements when necessary, stores normalized records, and tracks device status. This layer separates raw message exchange from application-level use. The HMI does not need to consume every edge message directly; instead, it can use processed historical records, summaries, device status, and acknowledgement information.

Persistent storage is required for engineering analysis and post-apply verification. Historical records allow the system developer and operator to observe trends, identify slow response or oscillation, compare control behavior under different parameters, and prepare data for auxiliary decision support. Device status tracking is also necessary because stale data, disconnection, or missing acknowledgements can affect the interpretation of control results.

## 1.5 HMI requirements for supervisory control

The HMI layer is one of the main layers of the developed system. Its role is to provide supervisory control and operator interaction. The HMI must not be limited to displaying the current temperature. It should provide a clear view of the current device state, historical behavior, parameter configuration, command results, alarms, and abnormal events.

For device monitoring, the HMI should show the measured temperature, setpoint, actuator output, controller state, device status, and relevant operating indicators. This information allows the operator to understand whether the system is stable, whether the temperature is approaching the setpoint, and whether the actuator is operating within expected limits.

Historical behavior viewing is also required. The operator must be able to compare current operation with previous periods and observe how the system responded after configuration changes. Such before-and-after observation is especially important when controller parameters are updated, because the value of a parameter change can be evaluated only by checking the subsequent process response.

The HMI must also support controlled parameter configuration. A parameter update should be applied through a clear operator action, transmitted to the edge device, and followed by visible command-result information. The operator should be able to see whether the command was sent, whether the edge device acknowledged it, and whether the system behavior changed after the new parameter version became active.

Alarm and abnormal event visibility is another important requirement. If the device becomes unavailable, measurements become stale, actuator output reaches an abnormal state, or the process moves outside an acceptable range, the HMI should make this condition visible. In this way, the HMI becomes part of the supervisory control process rather than only a passive dashboard.

## 1.6 Auxiliary decision-support role

The auxiliary decision-support mechanism is an additional support function in the developed system. It is not the main controller, not an autonomous optimizer, and not the central contribution of the thesis. Its role is to analyze stored behavior and prepare reviewable parameter recommendations that may help improve control quality.

Decision support depends on the data collected by the edge control layer and processed by the Data Hub layer. Historical temperature behavior, setpoint changes, actuator output, parameter versions, acknowledgement records, and post-apply results provide the basis for analyzing how the system reacted under different conditions. Without structured telemetry and persistent storage, such analysis would not be traceable.

The recommendation process must remain connected to operator supervision. A recommendation should be reviewed in the HMI before application. If the operator decides to apply it, the parameter update is sent through the normal command mechanism, acknowledged by the edge device, and checked using subsequent measurements. This means that decision support assists the operator but does not bypass the established control and verification workflow.

This boundary is important for the thesis. The main engineering result is the layered closed-loop temperature control and monitoring system. The auxiliary decision-support mechanism increases the value of the system by improving analysis and parameter preparation, while the operator remains in the loop and the system remains explainable and traceable.

## 1.7 Requirements for the developed system

The analysis of temperature-control process characteristics, closed-loop control principles, edge-based execution, data acquisition, HMI supervision, and auxiliary decision support leads to the requirements for the developed system. These requirements define the difference between a simple temperature-monitoring prototype and a complete layered closed-loop temperature control and monitoring system.

The requirements are grouped by the main system areas: the edge control layer, communication mechanism, Data Hub layer, HMI layer, auxiliary decision-support mechanism, and integrated system validation. This grouping reflects the architecture of the project and keeps the auxiliary functions separated from the main control and monitoring layers. The summarized requirements are presented in Table 1.1.

Table 1.1 – Main engineering requirements of the developed system

| Area | Requirement | Purpose |
|---|---|---|
| Edge control layer | Acquire temperature, execute local control, apply actuator output, maintain runtime parameters, publish telemetry, receive commands, and return acknowledgements | Local reliability and control continuity |
| Communication mechanism | Separate telemetry, commands, acknowledgements, and events using structured messages | Traceability and predictable data exchange |
| Data Hub layer | Ingest MQTT messages, parse payloads, store normalized records, and track device status | Data consistency and engineering analysis |
| HMI layer | Provide monitoring, history viewing, parameter configuration, and command-result visibility | Controlled operator interaction |
| Auxiliary decision-support mechanism | Analyze historical behavior and prepare reviewable parameter recommendations | Explainability and assisted decision-making |
| Validation | Test the complete path from measurement to post-apply observation | End-to-end verification |
