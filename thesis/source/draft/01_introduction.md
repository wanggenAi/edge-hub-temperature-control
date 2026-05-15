# 1 INTRODUCTION

## 1.1 Relevance and problem statement

Temperature control is a common engineering task in laboratory equipment, heating units, environmental chambers, embedded automation systems, and industrial processes. In such systems, the temperature value must not only be measured, but also maintained near a specified setpoint under the influence of disturbances, actuator limitations, sensor errors, thermal inertia, and communication delays. For this reason, a temperature-control system has to be considered not only as a controller, but as an engineering workflow that includes measurement, control action, supervision, configuration, feedback, and verification [1].

A common limitation of simple temperature-control prototypes is that they demonstrate either the local control algorithm or the monitoring interface, but do not always implement the complete engineering loop around the controlled object. In a practical system, the value of control is not determined only by the ability to calculate an actuator signal. It also depends on whether telemetry is transmitted in a structured form, whether commands are applied in a controlled and traceable way, whether parameter changes are acknowledged by the device, whether historical behavior is stored for analysis, and whether the operator can verify the result after a configuration change.

The diploma project is focused on the development of a layered closed-loop temperature control and monitoring system. The system includes an edge control layer, a Data Hub layer, an HMI layer, and an auxiliary decision-support mechanism. The edge layer performs local temperature acquisition and control execution. The Data Hub receives telemetry, parses control-related messages, stores historical data, tracks device state, and prepares information for higher-level processing. The HMI provides operator supervision, telemetry viewing, and parameter configuration. The decision-support mechanism helps analyze control behavior and prepare parameter recommendations, but it is treated as an auxiliary part of the system, not as the main subject of the work. MQTT-based exchange is used because it provides a lightweight publish-subscribe communication model suitable for device-to-service message flow [2].

The relevance of the project is determined by the need to connect embedded control, structured data exchange, persistent storage, operator interaction, and post-apply result checking into one reproducible engineering process. Therefore, the project is not limited to creating a temperature display, a separate PID controller, or an isolated web dashboard. Its purpose is to implement a complete control cycle: temperature measurement, local control, telemetry publishing, Data Hub ingestion, storage and processing, HMI monitoring, parameter update, device acknowledgement, and verification after the applied change.

The main engineering contribution of the project is the implementation of an end-to-end closed-loop platform in which local control, MQTT-based message exchange, Data Hub processing, persistent historical storage, HMI-based operation, parameter acknowledgement, and post-apply verification are integrated into one reproducible workflow. The auxiliary decision-support mechanism increases the engineering value of the system by supporting analysis and parameter preparation, while the operator remains in the loop and the system emphasizes explainability, feedback, and controlled evaluation rather than uncontrolled automatic optimization.

## 1.2 Aim and objectives of the project

The aim of the diploma project is to design, implement, and validate a layered closed-loop temperature control and monitoring system that combines an edge control layer, a Data Hub layer, an HMI layer, and an auxiliary decision-support mechanism for control-behavior analysis and parameter recommendation.

To achieve this aim, the following objectives must be completed:

- to analyze temperature control principles, monitoring requirements, and layered closed-loop architecture for an edge-based control system;
- to define the functional and non-functional requirements for the developed system;
- to design the architecture of the edge control layer, the Data Hub layer, and the HMI layer;
- to implement edge temperature acquisition, local control, runtime parameter handling, telemetry publishing, and command acknowledgement;
- to implement Data Hub MQTT ingestion, message parsing, telemetry filtering, aggregation, persistent storage, and device status tracking;
- to implement HMI monitoring, telemetry viewing, parameter configuration, and observation of control-related events;
- to include an auxiliary decision-support mechanism for analyzing control behavior and preparing parameter recommendations;
- to validate the complete closed loop, including telemetry generation, Data Hub ingestion, HMI monitoring, parameter update, device acknowledgement, and observation of system behavior after the applied change.

## 1.3 Object and subject of the project

The object of the project is an edge-based temperature control system considered as a closed-loop engineering platform. The platform combines local control execution with supervisory data processing, operator interaction, parameter adjustment, and evidence-based result checking.

The subject of the project is the architecture, communication flow, control logic, data processing pipeline, HMI interaction, parameter update mechanism, acknowledgement procedure, verification process, and auxiliary decision-support functions required to implement the complete temperature-control loop.

## 1.4 Practical significance

The practical significance of the project lies in the implementation of a complete layered prototype that demonstrates an industrial-style workflow for temperature control and monitoring. The system is not limited to displaying temperature values. It supports local control execution, structured MQTT communication, telemetry ingestion, time-series storage, operator interaction, parameter update, acknowledgement handling, and checking of the result after a new configuration is applied.

The edge layer provides a reproducible control environment based on an ESP32-oriented firmware structure and a simulation profile. This makes it possible to test control behavior before transferring the approach to physical hardware. The separation of local control from supervisory processing is important because time-critical actions remain close to the controlled object, while telemetry storage, analysis, visualization, and configuration are handled by higher software layers.

The Data Hub layer improves traceability by receiving telemetry, processing messages, storing historical values, and tracking device state. This allows the operator and the system developer to observe not only the current temperature, but also the sequence of events around parameter changes, acknowledgements, and control response. The HMI layer provides a practical interface for monitoring the system and applying configuration changes in a controlled way.

The auxiliary decision-support mechanism adds value by helping evaluate control behavior and prepare parameter recommendations. At the same time, the operator remains responsible for applying changes through the HMI and checking the result using stored measurements and acknowledgement information. This makes the prototype suitable as an engineering demonstration of a closed-loop control platform with traceable configuration, feedback, and verification. The developed system can also serve as a foundation for future hardware deployment, extension of control functions, or integration with additional monitoring tools.

## 1.5 Structure of the thesis

The thesis consists of seven main sections.

The first section introduces the relevance of the topic, states the engineering problem, defines the aim and objectives of the project, and describes the object, subject, and practical significance of the developed system.

The second section analyzes temperature control and monitoring systems. It considers feedback control principles, edge-based execution, telemetry exchange, HMI requirements, decision-support functions, and the requirements for the developed system.

The third section describes the system architecture. It explains the responsibilities of the edge control layer, the Data Hub layer, and the HMI layer, and presents the closed-loop flow of measurements, commands, acknowledgements, and feedback.

The fourth section describes the implementation of the edge control layer, including temperature acquisition, heater control, the control algorithm, runtime configuration, MQTT communication, and local response to parameter updates.

The fifth section describes the implementation of the Data Hub and HMI layers. It covers MQTT ingestion, message parsing, telemetry processing, persistent storage, backend services, frontend interaction, monitoring, and parameter configuration.

The sixth section describes the auxiliary decision-support mechanism and system validation. It explains how telemetry is used for behavior analysis, how recommendations are prepared, and how the complete loop is checked through telemetry generation, data ingestion, HMI operation, acknowledgement, and post-apply observation.

The seventh section summarizes the completed work, evaluates whether the project objectives have been achieved, and outlines possible directions for further improvement.

Thus, the thesis follows the engineering flow of the project: requirements analysis, architecture design, implementation of the main system layers, validation of the closed loop, and final evaluation of the obtained result.
