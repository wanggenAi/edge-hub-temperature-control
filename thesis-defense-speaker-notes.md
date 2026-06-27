# Speaker Notes

## 01. Design of Intelligent Edge and Time-Series Data Flow Temperature Control System

中文记忆：开场只讲题目和整体定位。不要急着讲细节。强调这不是只画设计图，而是做了一个端到端原型：边缘控制、数据流、存储、HMI 展示和 AI 辅助调参。

English speaking script:
Good morning, dear teachers. My thesis topic is Design of Intelligent Edge and Time-Series Data Flow Temperature Control System.

In this work, I designed and implemented an end-to-end prototype system for intelligent temperature control. The system includes an edge controller, MQTT telemetry, a reactive Data Hub, time-series storage, HMI monitoring, and AI-assisted PID parameter recommendation.

The word design in the title means system design and engineering realization. The project is not only a theoretical design. It also includes software implementation, integration, and prototype-level validation.

## 02. Objective And Implemented Scope

中文记忆：这一页回答“你到底做了什么”。按五层讲：硬件控制、MQTT、Data Hub、HMI、AI。最后补一句 design 不等于没实现。

English speaking script:
The objective of the project is to build an end-to-end intelligent temperature-control prototype.

The implemented scope has five parts. First, the edge device performs local closed-loop control. Second, MQTT is used for telemetry upload and parameter downlink. Third, the Data Hub consumes and processes telemetry as a reactive data flow. Fourth, the HMI provides monitoring, alarms, history, and operation functions. Fifth, the AI module supports PID tuning by generating and ranking parameter candidates.

So the business value is that the temperature-control process becomes observable, traceable, and adjustable. A user can see the system state, understand control quality, receive optimization suggestions, and send confirmed parameter updates back to the device.

## 03. Requirements And Design Goals

中文记忆：这页讲为什么要分层。实时控制放边缘端；数据和观察放 Data Hub/HMI；AI 只是辅助决策。四个设计目标：安全、可观测、可追溯、可维护。

English speaking script:
The system requirements come from both control and operation.

On the control side, the system must acquire temperature, calculate control output, and drive the heater through PWM. On the data side, it must upload telemetry, store historical data, and support query and visualization. On the operation side, it must support alarms, device management, parameter management, AI recommendations, and command acknowledgement.

The main design goals are safety, observability, traceability, and maintainability. Safety means the edge device can protect the heater even if the network or upper-layer services fail. Observability means key telemetry and metrics can be seen. Traceability means parameter changes and ACK results are recorded. Maintainability means each layer has a clear responsibility.

## 04. End-to-End Closed Loop Architecture

中文记忆：这一页讲闭环，不是单向展示。数据从硬件上来，AI/HMI 做分析和确认，参数再下发，设备 ACK，之后系统评估效果。强调人参与确认，AI 不直接控制硬件。

English speaking script:
This slide shows the end-to-end closed-loop architecture.

The edge device reads temperature, performs the control loop, and uploads telemetry through MQTT. The Data Hub receives the telemetry, validates it, filters or aggregates it, and writes it into time-series storage. Then the HMI and AI modules use the stored and live data for monitoring, diagnosis, recommendation, and operation.

The reverse direction is also important. The AI module can recommend PID parameter candidates, but it does not directly actuate the heater. A human operator reviews the preview result in the HMI and confirms the update. The confirmed parameter set is sent to the edge device, and the edge returns an ACK. After that, the system can compare post-apply behavior with the previous behavior.

This forms a human-in-the-loop optimization workflow.

## 05. Edge Control, Hardware Safety And Firmware

中文记忆：硬件层讲三个重点：器件选择、安全保护、控制目标。器件名字要记住：ESP32-WROOM-32、DS18B20、NMOS3400、thermal switch、NVS。热保护开关串在加热器供电路径里，温度过高硬件断开。

English speaking script:
The edge layer contains both hardware and firmware design.

For the controller, I use the ESP32-WROOM-32 module. It provides enough computing capability, Wi-Fi connectivity, GPIO control, and non-volatile storage. For temperature sensing, I use the DS18B20 digital temperature sensor, with a pull-up resistor on the one-wire bus. For heater control, GPIO18 outputs PWM to the NMOS3400 MOSFET, which works as a low-side heater switch.

The hardware also includes engineering safety considerations. A thermal switch, or over-temperature protection switch, is placed in the heater power path. If the temperature becomes too high, it opens the circuit and cuts heater power independently from the ESP32 firmware. In addition, the MOSFET gate has a series resistor and a pull-down resistor, and the power rails have decoupling capacitors for stability.

In firmware, the control target range is limited from 20 to 60 degrees Celsius, and the software maximum safe temperature is 65 degrees Celsius. If the sensor is invalid or the measured temperature exceeds this safety threshold, the fault latch forces PWM output to zero. The controller supports PID-compatible parameters, output limiting, and anti-windup. Runtime parameters are stored in ESP32 NVS using the Preferences API, so the device can keep the latest configuration after restart.

## 06. Telemetry And Control Metrics

中文记忆：这一页回答“为什么上传这些参数”。不是随便传，是为了观察控制质量、做告警、做 AI 特征。注意不要说没有证据的具体优化百分比，只讲指标定义和用途。

English speaking script:
The telemetry fields are selected according to the control objective.

The system uploads temperature, setpoint, control error, PWM duty, saturation state, PID parameters, control mode, sensor validity, fault latch state, timestamp, device ID, and run ID. These fields allow the upper layers to reconstruct what happened during the control process.

From telemetry, we can calculate control-quality metrics. Mean absolute error describes average tracking error. Overshoot describes whether the temperature goes beyond the target. Settling time describes how fast the system becomes stable. In-band ratio describes how often the temperature stays within the acceptable band. Temperature swing describes oscillation amplitude, and saturation ratio describes whether the actuator is often limited by its maximum output.

These metrics are used for HMI display, alarm rules, AI feature extraction, recommendation preview, and post-apply evaluation.

## 07. Reactive Data Hub And Time-Series Flow

中文记忆：Data Hub 讲三个亮点：Reactor 非阻塞处理、过滤/聚合、告警状态机。为什么要聚合？因为温控数据很多时候稳定，如果每条都存，会浪费存储、增加查询压力；但是完全丢掉又看不到趋势，所以把稳定窗口汇总成 summary。

English speaking script:
The Data Hub is the middle layer between edge devices and upper applications.

The workload is mainly I/O-bound: MQTT input, validation, database writing, and metrics reporting. Therefore, I use Java, Spring Boot, HiveMQ MQTT client, and Project Reactor. The pipeline is non-blocking and uses bounded buffers and backpressure, so burst telemetry does not simply create unlimited threads or memory usage.

The pipeline consumes MQTT messages, parses and validates payloads, applies persistence policy, writes telemetry or summaries, and then sends acknowledgement at the pipeline level. Device-lane processing keeps messages from the same device ordered while still allowing parallel processing across devices.

Aggregation is an important design point. Temperature telemetry can be very frequent, and when the system is stable, many samples are almost duplicate. If all duplicate samples are stored, the database grows quickly and historical queries become heavier. But if they are simply dropped, the operator loses information about that time window. Therefore, the Data Hub filters steady-state duplicate telemetry and generates summary records, including sample count, time window, average temperature, min and max values, error metrics, and actuator statistics.

The alarm layer also uses rule-state filtering. For example, out-of-band, invalid sensor, saturation, fault latch, and max-safe-temperature conditions are converted into alarm facts without creating repeated alarm noise.

## 08. AI-Assisted PID Recommendation

中文记忆：AI 模型不是直接控制温度。它做两件事：第一，对候选 PID 参数排序；第二，估计改善可能性和 preview 风险。完整流程是规则诊断生成候选，模型排序，preview 打分，人确认后下发。

English speaking script:
The AI module is used for decision support, not for direct temperature control. The real-time PWM output is still generated by the edge PID-compatible controller.

The first layer is rule-based. It reads a telemetry window and extracts features such as mean error, mean absolute error, error standard deviation, temperature swing, overshoot, settling time, in-band ratio, zero crossings, and saturation ratio. Based on these features, it diagnoses control problems such as slow response, steady-state error, overshoot, oscillation, saturation-limited behavior, or normal behavior.

Then the tuning engine generates conservative PID candidate parameters. For example, if response is slow, it can increase proportional or integral action carefully. If overshoot or oscillation is high, it can reduce aggressive gains and use more cautious candidates.

The machine-learning layer is used to rank these candidates. The training scripts support models such as Logistic Regression and Random Forest, and the active model artifacts are loaded as joblib files. The model estimates whether a candidate is likely to improve the result and whether the preview gap risk is low, medium, or high.

The ranking formula is: success_score equals P improved minus 0.5 times P unchanged minus P worse. gap_score equals P low gap minus 0.5 times P medium gap minus P high gap. Finally, total_score equals 0.65 times success_score plus 0.35 times gap_score.

After ranking, the preview simulates the PID response with a thermal model. The user sees the preview in the HMI, confirms the parameter update, and then the system evaluates the actual post-apply effect.

## 09. Deployment, Pressure Test And Operations

中文记忆：这一页讲工程落地，不要说夸张性能数字。部署要分清楚：ESP32 固件是烧录到硬件或用 simulator；软件侧服务用 Docker / Docker Compose 组织，比如 MQTT、Data Hub、TDengine、PostgreSQL、HMI 和 AI 服务。再讲压测 baseline、metrics 观察、数据库维护脚本。

English speaking script:
The system is deployed as several cooperating components.

At the bottom, there is the edge firmware or simulator. The edge firmware is deployed to the ESP32 device separately, while the software-side services can be organized with Docker Compose. This includes the MQTT broker, Java Data Hub, TDengine, PostgreSQL, HMI backend and frontend, and AI-related services.

MQTT is used as the communication channel. The Java Data Hub subscribes to telemetry and writes processed data into TDengine. PostgreSQL stores management data for the HMI and AI services. The HMI provides user-facing monitoring and control.

For validation, I checked the end-to-end telemetry path, from edge output to database storage and HMI display. I also validated the parameter set workflow: the user sends parameters, the edge validates them, applies or rejects them, and sends an ACK.

For the Data Hub, I performed pressure testing to observe the baseline behavior of the machine and pipeline. The goal is not only to get a single performance number, but to understand throughput, queue behavior, dropped or failed records, and error indicators under continuous telemetry input.

The project also includes metrics monitoring and database maintenance scripts, so the system can be operated and cleaned during development and testing.

## 10. Results, Limitations And Future Work

中文记忆：结尾强调“已经实现了什么”，同时承认限制。不要硬吹效果数据。说原型已经打通闭环，未来可以扩展实验、硬件保护、模型生命周期和部署监控。

English speaking script:
In conclusion, this work implemented an end-to-end prototype for intelligent temperature control.

The main result is that the edge controller, hardware safety logic, MQTT telemetry, Data Hub processing, time-series storage, HMI operation, AI recommendation, parameter downlink, edge ACK, and post-apply evaluation are connected into one workflow.

The project also has limitations. The validation is still prototype-level. More physical thermal-load experiments should be performed, and longer-term quantitative datasets are needed for stronger model evaluation.

For future work, I would improve the hardware protection and enclosure, test more devices and scenarios, strengthen the model lifecycle, and improve deployment automation and monitoring.

Overall, the contribution of this thesis is the design and implementation of a layered, observable, and human-in-the-loop intelligent temperature-control system.
