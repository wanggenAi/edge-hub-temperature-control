# 2 ARCHITECTURE OF THE DEVELOPED SYSTEM

## 2.1 General architecture of the system

The developed system is designed as a layered closed-loop temperature control and monitoring system. Its architecture separates time-critical local control from supervisory data processing and operator interaction. This separation is necessary because the temperature-control process must continue at the edge, while monitoring, storage, parameter configuration, and analysis can be performed by upper layers. Figure 2.1 presents the general architecture of the developed system and shows the relationship between the three main layers and the auxiliary decision-support mechanism.

The architecture contains three main layers: the edge control layer, the Data Hub layer, and the HMI layer. The edge control layer interacts directly with the controlled object and executes the local feedback process. The Data Hub layer receives MQTT messages, parses them, stores normalized records, and maintains device status. The HMI layer provides operator supervision, history viewing, parameter configuration, and command-result visibility. The auxiliary decision-support mechanism is connected to the HMI and stored data, but it is not a separate main control layer and does not replace the operator.

The main architectural decision is to treat the system as an engineering workflow rather than as a set of independent modules. A temperature measurement is not only displayed to the user; it becomes part of a traceable sequence that includes control execution, telemetry publishing, message ingestion, storage, HMI observation, parameter update, device acknowledgement, and post-apply verification. As shown in Figure 2.1, the three main layers are aligned around the closed-loop measurement, command, and verification path, while the auxiliary decision-support mechanism remains outside the main control chain. The layered structure of the developed system is summarized in Table 2.1.

Table 2.1 – Architectural areas of the developed system

| Area | Main responsibility | Main exchanged information |
|---|---|---|
| Edge control layer | Local measurement, control execution, actuator output, runtime parameter handling, telemetry publishing, command receiving, and acknowledgement | Temperature, setpoint, controller parameters, actuator output, device state, acknowledgement data |
| Data Hub layer | MQTT ingestion, payload parsing, filtering, aggregation, persistent storage, and device-status tracking | Telemetry records, parameter commands, acknowledgements, summaries, status events |
| HMI layer | Operator monitoring, history viewing, parameter configuration, command-result observation, and abnormal-event visibility | Current state, historical data, parameter forms, command status, alarms |
| Auxiliary decision-support mechanism | Analysis of stored behavior and preparation of reviewable parameter recommendations | Historical windows, control-performance features, recommendation metadata, post-apply comparison |

The three main layers are connected through a common communication and data model. MQTT is used for runtime message exchange between the edge device and upper layers [2], while persistent storage provides the historical basis for monitoring, analysis, and verification. This approach allows each layer to have a clear responsibility while still supporting an end-to-end control workflow.

## 2.2 Edge control layer

The edge control layer is the execution core of the system. It is responsible for acquiring temperature data, comparing the measured value with the setpoint, calculating the local control action, and applying the actuator output. In the developed project, the edge node is represented by an ESP32-oriented firmware structure and a Wokwi simulation profile. This makes it possible to test the control workflow in a repeatable environment while keeping the structure suitable for later hardware deployment.

The edge layer must remain operational even when the HMI, database, or network connection is temporarily unavailable. For this reason, the local control algorithm and actuator output are not delegated to the Data Hub or the HMI. The edge device continues to use the last valid runtime configuration and publishes its state when communication is available. This design protects the time-critical part of the control loop from supervisory-layer delays.

Besides local control, the edge layer participates in the wider engineering loop. It publishes structured telemetry with process values and controller state, receives parameter commands, validates or applies updated parameters, and returns acknowledgements. The acknowledgement is important because it distinguishes a command that was only sent from a command that was actually processed by the device.

The telemetry produced by the edge layer includes not only the current temperature but also engineering context such as setpoint, control output, controller coefficients, timing information, safety state, connectivity state, and pending-parameter status. These fields allow the upper layers to interpret process behavior and to verify changes after new parameters are applied.

## 2.3 Data Hub layer

The Data Hub layer is the processing center between the edge device and the HMI. Its role is to receive MQTT messages, classify them by topic and payload type, transform them into stable internal records, and store them for later use. This layer prevents the HMI from depending directly on raw device messages and provides a consistent data source for monitoring, history, alarms, and analysis.

In the developed system, the Data Hub subscribes to telemetry, parameter-command, acknowledgement, and configuration-update topics. The ingestion pipeline must handle messages in a controlled way, because data can arrive faster than it can be written to storage or displayed to the user. Therefore, the layer includes bounded processing and backpressure concepts. This is important for engineering reliability because uncontrolled buffering can hide overload until the system becomes unstable.

Persistent storage is a central responsibility of the Data Hub. Telemetry records, parameter commands, acknowledgements, summaries, and device-status events are stored so that system behavior can be reconstructed later. This is required for traceability and for post-apply verification. If the operator changes controller parameters, the stored records show which command was sent, whether the device acknowledged it, what parameter version became active, and how the temperature behavior changed afterwards.

The Data Hub also supports device-status tracking. Online or offline state, stale telemetry, missing acknowledgements, and abnormal process conditions affect how the operator should interpret the HMI view. By maintaining status information separately from raw telemetry, the system can present a clearer operational picture.

## 2.4 HMI layer

The HMI layer is the operator-facing part of the system. Its role is not limited to displaying a temperature value. It provides access to current device state, historical behavior, parameter configuration, command status, alarms, and post-apply observations. The HMI is therefore the supervisory control layer through which the operator interacts with the developed system.

For monitoring, the HMI displays current temperature, setpoint, actuator output, controller state, connectivity state, and relevant abnormal conditions. For historical analysis, it allows the operator to inspect behavior over time and compare operation before and after parameter changes. This is necessary because the effect of a temperature-control parameter update cannot be evaluated from a single measurement.

The HMI also provides the controlled path for parameter configuration. When the operator applies a new setpoint or controller parameter set, the HMI initiates a parameter command through the system command path. The corresponding upper-layer service publishes the command to the device-specific MQTT topic. The result must not be treated as successful only because the message was published. The HMI should show whether the edge device returned an acknowledgement and whether the subsequent measurements confirm the expected behavior.

This design keeps the operator in the loop. Even when an auxiliary recommendation is available, the HMI remains the place where the recommendation is reviewed, applied, and checked. This boundary is important because the system is intended as a traceable engineering prototype rather than an autonomous optimization product.

## 2.5 Closed-loop data and command flow

The central system behavior is the closed-loop flow from measurement to post-apply verification. At the local level, the edge device measures temperature, calculates the control action, applies actuator output, and repeats this process. At the system level, the same control process is extended by structured communication, storage, HMI supervision, and controlled parameter updates.

The normal telemetry path begins when the edge device publishes a message containing the measured temperature, setpoint, control output, controller state, and related status fields. The Data Hub ingests this message, parses it, stores a normalized record, and updates status information. The HMI then uses the stored and processed data to display current and historical behavior to the operator.

The command path begins when an operator changes a parameter through the HMI. The HMI initiates a parameter-set operation, and the upper-layer command path publishes the corresponding message to the device-specific MQTT topic. The edge device receives the command, validates its content, applies or stages the new parameters according to the command semantics, and publishes an acknowledgement. The Data Hub stores the command and acknowledgement records, while the HMI displays the result to the operator.

Post-apply verification closes the engineering loop. After the acknowledgement is received, later telemetry is observed to determine whether the process behavior changed as expected. This step is essential because an acknowledgement only confirms that the device processed the command; it does not prove that the control behavior improved. The sequence of the developed workflow is summarized in Table 2.2.

Table 2.2 – Closed-loop workflow of the developed system

| Step | Responsible layer | Purpose |
|---|---|---|
| Temperature measurement and local control | Edge control layer | Maintain local feedback control near the controlled object |
| Telemetry publishing | Edge control layer | Send structured process and controller state to upper layers |
| Message ingestion and storage | Data Hub layer | Preserve telemetry and status records for monitoring and analysis |
| Operator monitoring | HMI layer | Display current and historical behavior in a supervisory interface |
| Parameter update | HMI layer | Send controlled configuration changes through the command path |
| Device acknowledgement | Edge control layer and Data Hub layer | Confirm whether the command was processed and store the result |
| Post-apply verification | Data Hub layer and HMI layer | Compare subsequent behavior with the previous operating state |

This flow shows that the developed architecture is not a simple one-way monitoring chain. It contains feedback at the control level and traceability at the engineering-system level.

## 2.6 Communication protocol and data model

MQTT is used as the main runtime communication protocol between the edge device and the upper layers. The topic structure separates telemetry, commands, acknowledgements, and configuration events. This separation is necessary because each message type has a different meaning and must be processed differently by the Data Hub and HMI.

The device-scoped topic structure allows the system to address a specific edge node. Telemetry is published from the device to the upper layers. Parameter-set messages are published through the upper-layer command path to the edge device. Acknowledgement messages are published by the edge device after it handles a parameter command. Configuration-related messages can also be extended for alarm rules, storage rules, or other supervisory settings when required.

The telemetry payload is structured as JSON and contains identity, process values, controller state, output state, timing quality, safety state, and communication state. Important fields include device identifier, run identifier, measured or simulated temperature, setpoint, error, control output, PWM value, controller coefficients, control period, sensor validity, fault state, MQTT connection state, and pending-parameter information.

The parameter-set payload contains the values that may change during runtime, such as setpoint, controller coefficients, control period, control mode, and apply semantics. Additional metadata, such as source and request time, can be stored for traceability. The acknowledgement payload contains the device identifier, acknowledgement type, success flag, applied parameter values, reason, safety state, and related runtime information.

This data model is intentionally explicit. It makes the system easier to test because every important transition can be observed in messages or storage records. It also supports later extension because additional fields can be added without changing the main topic separation.

## 2.7 Auxiliary decision-support interface

The auxiliary decision-support mechanism is connected to the architecture through stored telemetry, parameter records, and HMI actions. It analyzes historical behavior and prepares parameter recommendations, but it does not control the actuator directly and does not bypass the normal command path.

The input for decision support comes from the Data Hub and HMI data sources: telemetry windows, setpoint changes, actuator output, controller coefficients, acknowledgement records, and post-apply results. This context allows the mechanism to identify slow response, overshoot, oscillation, or poor settling behavior.

The output of decision support is a reviewable recommendation rather than an automatic control action. It may include proposed parameter values and supporting information for the operator. Before affecting the system, it must be reviewed in the HMI and applied through the same parameter-set mechanism used for manual configuration. After application, the edge device must acknowledge the command and later telemetry must be checked, keeping the auxiliary mechanism explainable and traceable within the main architecture.
