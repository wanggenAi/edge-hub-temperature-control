# EdgeHub 源码地图与答辩导读

本文档按“系统分层 -> 核心功能 -> 代码位置 -> 实现思路 -> 答辩说法”解释当前项目，目标不是替代 README，而是帮助你快速理解每一层为什么存在、运行时怎么连起来、被追问时应该打开哪段源码。

代码链接固定到当前 commit：

- GitHub 基准链接：`https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/`
- 本地仓库：`/Users/seker./edge-hub-temperature-control`

如果以后代码继续改动，固定 commit 链接仍能打开当时版本；如果想看最新代码，把链接里的 commit 哈希替换成 `main`。

## 0. 如何和论文一起读

本源码地图已参考你的论文终稿：

- 论文文件：`thesis/generated/drafts/thesis_draft_final_format_fixed_quantified.docx`
- 可读 Markdown 源稿：[`thesis/source/draft/03_architecture.md`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/thesis/source/draft/03_architecture.md), [`04_edge_control.md`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/thesis/source/draft/04_edge_control.md), [`05_data_hub_hmi.md`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/thesis/source/draft/05_data_hub_hmi.md), [`06_decision_support_validation.md`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/thesis/source/draft/06_decision_support_validation.md)

论文和源码之间的主对应关系：

| 论文章节 | 论文主张 | 源码证据 |
|---|---|---|
| 3.1-3.5 架构与闭环流程 | 系统是 layered closed-loop workflow，不是单向监控链 | [`README.md#L1-L51`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/README.md#L1-L51), [`docs/architecture-overview.md#L1-L57`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/docs/architecture-overview.md#L1-L57), 本文第 10 节三条链路 |
| 3.6 通信协议与数据模型 | MQTT 拆分 telemetry / params/set / params/ack | [`docs/mqtt_interface.md#L1-L116`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/docs/mqtt_interface.md#L1-L116), [`TelemetryBuilder`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/comms/mqtt/telemetry_builder.cpp#L19-L94), [`HubMessageParser`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/parser/HubMessageParser.java#L25-L39) |
| 4.1 控制目标和边界 | 默认 23 °C，操作范围 20-60 °C，软件安全限值 65 °C；仿真验证不等于硬件实测 | [`app_config.h#L13-L29`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/config/app_config.h#L13-L29), [`param_validator.cpp#L13-L42`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/comms/mqtt/param_validator.cpp#L13-L42) |
| 4.5 温度测量、反馈和控制算法 | Wokwi 中 DS18B20 是参考，实际受控变量来自虚拟热模型；控制器是 PID 兼容、默认 PI 行为 | [`edge_app.cpp#L231-L267`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/app/edge_app.cpp#L231-L267), [`thermal_plant_model.cpp#L5-L9`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/hardware/wokwi/thermal_plant_model.cpp#L5-L9), [`pi_controller.cpp#L9-L60`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/controller/pi_controller.cpp#L9-L60) |
| 4.6 运行时配置、MQTT、安全 | 参数可部分更新、校验、立即应用或暂存，并返回 ACK；本地安全强制关断 | [`param_update_handler.cpp#L22-L93`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/comms/mqtt/param_update_handler.cpp#L22-L93), [`runtime_config_store.cpp#L14-L71`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/app/runtime_config_store.cpp#L14-L71), [`edge_app.cpp#L220-L255`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/app/edge_app.cpp#L220-L255) |
| 5.1-5.3 Data Hub | 有边界队列、Reactor 背压、解析、过滤、摘要、TDengine 写入 | [`ReactiveMqttConsumer.java#L43-L67`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/mqtt/ReactiveMqttConsumer.java#L43-L67), [`MqttConsumePipeline.java#L162-L227`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/pipeline/MqttConsumePipeline.java#L162-L227), [`TelemetryWriteFilter.java#L46-L101`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/pipeline/TelemetryWriteFilter.java#L46-L101) |
| 5.4 告警与规则 | 告警是监视与追溯，不是自动控制；包含状态机避免抖动 | [`AlarmRuleEngineService.java#L46-L75`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/alarm/AlarmRuleEngineService.java#L46-L75), [`AlarmRuleEngineService.java#L237-L320`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/alarm/AlarmRuleEngineService.java#L237-L320) |
| 5.5-5.6 HMI | 前端不是 MQTT 客户端；后端提供受控参数下发、权限、ACK-aware confirmation | [`devices.py#L1644-L1706`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1644-L1706), [`mqtt_publisher.py#L29-L125`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/mqtt_publisher.py#L29-L125), [`deps.py#L22-L84`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/deps.py#L22-L84) |
| 6.1-6.3 决策支持 | 决策支持不是主控制器；基于特征、规则分类和保守参数建议 | [`feature_extractor.py#L37-L80`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/feature_extractor.py#L37-L80), [`problem_classifier.py#L7-L69`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/problem_classifier.py#L7-L69), [`tuning_engine.py#L18-L91`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/tuning_engine.py#L18-L91) |
| 6.4-6.7 验证 | 验证的是软件平台、仿真边缘行为、存储 telemetry 和 HMI 演示数据；不是最终工业硬件认证 | [`post_effect_evaluator.py#L27-L94`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/post_effect_evaluator.py#L27-L94), [`control_action_learning.py#L522-L831`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/control_action_learning.py#L522-L831) |

答辩时可以按“论文主张 -> 源码位置 -> 运行证据”三步讲。例如老师问“你说 ACK-aware confirmation，代码在哪里？”你就打开 `devices.py` 的参数更新接口和 ACK 等待函数，再打开设备端 `param_update_handler.cpp`。

## 1. 一句话总览

本项目是一个端到端智能温控平台：边缘端执行温度闭环控制，通过 MQTT 上报遥测和接收参数；Java Data Hub 消费 MQTT、解析、限流、告警、写入 TDengine；HMI 后端提供认证、设备、历史、告警、AI 推荐和 MQTT 下发能力；React 前端把这些能力组织成操作员界面；AI/ML 层完成特征提取、问题诊断、PID 参数建议、预览仿真和应用后验证。

主运行链路：

```text
ESP32/Wokwi 边缘控制
-> MQTT telemetry / params/set / params/ack
-> Java Data Hub 消费、解析、告警、摘要、入库
-> TDengine 时序数据 + PostgreSQL 控制平面
-> FastAPI 后端 API / WebSocket / AI 推荐 / MQTT 下发
-> React HMI 页面展示、人工确认和运维观察
```

## 2. 仓库层级地图

| 层级 | 目录 | 核心职责 | 入口/关键文件 |
|---|---|---|---|
| 边缘控制层 | `simulator/wokwi` | 温度采样、PI/PID 控制、PWM 输出、MQTT 遥测、参数接收与 ACK | [`sketch.ino`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/sketch.ino#L17-L47), [`edge_app.cpp`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/app/edge_app.cpp#L83-L118) |
| 通信协议层 | `docs/mqtt_interface.md`, `simulator/.../comms/mqtt`, `data-hub/.../mqtt`, `hmi/backend/.../mqtt_publisher.py` | 统一 MQTT 主题和 JSON 字段，区分遥测、下发意图和设备确认 | [`mqtt_gateway.cpp`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/comms/mqtt/mqtt_gateway.cpp#L88-L152), [`mqtt_publisher.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/mqtt_publisher.py#L29-L55) |
| 数据中枢层 | `data-hub` | MQTT 消费、背压控制、解析、告警、设备状态、摘要、TDengine 写入 | [`ReactiveMqttConsumer`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/mqtt/ReactiveMqttConsumer.java#L43-L67), [`MqttConsumePipeline`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/pipeline/MqttConsumePipeline.java#L162-L188) |
| HMI 后端层 | `hmi/backend` | FastAPI API、JWT/RBAC、设备管理、历史查询、AI 推荐、MQTT 参数下发 | [`main.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/main.py#L15-L54), [`devices.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1290-L1706) |
| HMI 前端层 | `hmi/frontend` | React 页面、路由、API 封装、实时设备状态、AI/告警/历史/运维界面 | [`router.tsx`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/routes/router.tsx#L34-L52), [`api.ts`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/lib/api.ts#L94-L253) |
| AI 决策层 | `hmi/backend/app/services/ai` | 特征提取、问题分类、参数建议、候选排序、预览仿真、效果评估 | [`recommendation_service.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/recommendation_service.py#L35-L76), [`preview_simulator.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/preview_simulator.py#L152-L208) |
| 离线学习层 | `ml`, `hmi/backend/ai/scripts` | TDengine 数据导出、训练窗口、特征、伪标签、反馈样本、模型生命周期 | [`export_tdengine_data.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/export_tdengine_data.py#L188-L251), [`extract_features.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/extract_features.py#L117-L264) |
| 硬件/论文/部署支撑 | `hardware`, `docs`, `thesis`, `scripts` | 硬件说明、部署说明、论文素材、演示和压测脚本 | [`README.md`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/README.md#L1-L51), [`docs/architecture-overview.md`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/docs/architecture-overview.md#L1-L57) |

## 3. 边缘控制层：设备端如何闭环控制

### 3.1 入口与对象装配

入口在 [`simulator/wokwi/src/sketch.ino`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/sketch.ino#L17-L47)。

关键点：

- `BuildConfig()` 根据 `EDGE_BUILD_SIMULATOR` 决定是否优先使用模拟反馈。
- 模拟环境用 Wokwi 的 DS18B20 和 PWM heater，真实硬件 profile 则切换到 real sensor / MOSFET heater。
- `MqttGateway`、传感器、执行器一起注入 `EdgeTemperatureApp`，这体现了边缘端也做了分层，而不是把所有逻辑塞进 `loop()`。

答辩说法：

> 边缘端入口只负责装配对象，真正的控制周期、通信和安全逻辑都封装在 `EdgeTemperatureApp`，这样同一套应用逻辑可以在 Wokwi 仿真和真实硬件 profile 之间切换。

### 3.2 启动与主循环

启动和主循环在 [`edge_app.cpp`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/app/edge_app.cpp#L83-L118)。

实现方式：

- `setup()` 初始化串口、状态灯、传感器、执行器和 MQTT，并注册参数消息回调。
- `loop_once()` 每轮维护 MQTT 连接、更新心跳、执行一次控制周期检查。
- 控制周期不等于主循环周期，真正是否控制由 `run_control_tick()` 根据 `control_period_ms` 判断。

### 3.3 控制周期

核心控制过程在 [`run_control_tick()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/app/edge_app.cpp#L203-L272)：

1. 根据运行时配置判断是否到达控制周期。
2. 先处理暂存的参数更新。
3. 读取传感器并判断是否有效。
4. 如果传感器无效或超过软件安全温度，锁存故障并强制输出为 0。
5. 如果安全状态正常，调用 PI/PID 控制器计算 PWM。
6. 在仿真模式下更新热模型。
7. 构造遥测快照，序列化为 JSON 并通过 MQTT 发布。

安全逻辑位置：

- 故障锁存：[`latch_fault()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/app/edge_app.cpp#L165-L176)
- 过温和传感器判断：[`run_control_tick()` 220-229 行](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/app/edge_app.cpp#L220-L229)
- 安全强制关断：[`run_control_tick()` 243-255 行](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/app/edge_app.cpp#L243-L255)

### 3.4 PI/PID 算法

控制器在 [`pi_controller.cpp`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/controller/pi_controller.cpp#L9-L60)。

实现重点：

- 误差：`target_temp_c - measured_temp_c`。
- `p_control` 模式会把 `ki` 和 `kd` 置 0。
- 导数项做一阶滤波，减少噪声带来的抖动。
- 积分项有上下限，并带 anti-windup：如果输出已经高饱和且误差仍推动升高，或低饱和且误差仍推动降低，就不继续累积积分。
- 最终输出被限制在 `0..max_duty`，再转成 PWM duty 和归一化值。

答辩说法：

> 这里不是简单比例控制，而是带积分限幅、导数滤波和饱和保护的 PID 兼容实现。当前参数可让 `kd=0` 表现为 PI 控制，但接口保留 `kd`，方便后续扩展。

### 3.5 MQTT 参数接收与 ACK

设备端 MQTT 网关在 [`mqtt_gateway.cpp`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/comms/mqtt/mqtt_gateway.cpp#L12-L152)。

关键逻辑：

- 连接成功后订阅 `params/set`：[`ensure_mqtt()` 88-97 行](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/comms/mqtt/mqtt_gateway.cpp#L88-L97)
- 收到消息时只接受配置的 `params_set_topic`：[`handle_mqtt_message()` 32-53 行](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/comms/mqtt/mqtt_gateway.cpp#L32-L53)
- 发布遥测：[`publish_telemetry()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/comms/mqtt/mqtt_gateway.cpp#L115-L130)
- 发布 ACK：[`publish_ack_json()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/comms/mqtt/mqtt_gateway.cpp#L132-L152)

参数处理在 [`param_update_handler.cpp`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/comms/mqtt/param_update_handler.cpp#L22-L72)：

- 解析失败：发 `parse_error` ACK。
- 校验失败：发 `validation_error` ACK。
- `apply_immediately=true`：立即写入运行时配置，重置积分，发 `applied` ACK。
- 否则：先暂存参数，控制周期中再应用，发 `staged` 或 `pending_applied` ACK。

运行时配置写入在 [`runtime_config_store.cpp`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/app/runtime_config_store.cpp#L14-L71)，支持只更新 payload 中出现的字段。

### 3.6 遥测 JSON

遥测字段由 [`build_snapshot()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/app/edge_app.cpp#L299-L338) 收集，由 [`TelemetryBuilder::to_json()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/comms/mqtt/telemetry_builder.cpp#L19-L94) 序列化。

字段分组：

- 设备身份：`device_id`, `run_id`, `uptime_ms`
- 温控过程：`target_temp_c`, `sim_temp_c`, `sensor_temp_c`, `error_c`
- 控制输出：`control_output`, `pwm_duty`, `pwm_norm`, `saturation_state`
- 控制器参数：`control_mode`, `kp`, `ki`, `kd`
- 安全和通信状态：`sensor_valid`, `fault_latched`, `wifi_connected`, `mqtt_connected`
- 参数下发状态：`has_pending_params`, `pending_params_age_ms`

## 4. MQTT 协议层：为什么要拆 telemetry / set / ack

协议说明在 [`docs/mqtt_interface.md`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/docs/mqtt_interface.md#L1-L116)。

当前实现的主题：

- `edge/temperature/<device_id>/telemetry`
- `edge/temperature/<device_id>/params/set`
- `edge/temperature/<device_id>/params/ack`
- `edgehub/config/alarm-rules/updated`
- `edgehub/config/storage-rules/updated`

设计意义：

- `telemetry` 是设备观测事实。
- `params/set` 是上位系统的控制意图。
- `params/ack` 是设备处理结果。

答辩说法：

> 下发成功不等于设备真正应用成功，所以项目把参数意图和设备 ACK 拆成两个事实。这样 HMI 可以等待 ACK，Data Hub 可以同时归档意图和结果，AI 的应用后验证也有可追溯基础。

## 5. Data Hub 层：MQTT 到 TDengine 的可靠通道

### 5.1 Spring Boot 入口

入口在 [`DataHubApplication.java`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/DataHubApplication.java#L8-L15)，启用：

- Spring Boot 自动配置
- `@ConfigurationPropertiesScan` 读取配置
- `@EnableScheduling` 支持周期性摘要 flush 和离线状态检查

### 5.2 MQTT 消费入口

[`ReactiveMqttConsumer`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/mqtt/ReactiveMqttConsumer.java#L43-L67) 负责连接 HiveMQ MQTT client，并把收到的消息推入 Reactor sink。

实现重点：

- 使用 bounded source queue：[`43-52 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/mqtt/ReactiveMqttConsumer.java#L43-L52)
- 自动重连和重订阅：[`88-157 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/mqtt/ReactiveMqttConsumer.java#L88-L157)
- 收到消息后解析 topic 中的 `deviceId` 并构造 `MqttEnvelope`：[`168-181 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/mqtt/ReactiveMqttConsumer.java#L168-L181)
- 入口溢出时记录指标并 ACK，避免 QoS1 inflight 被卡死：[`192-214 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/mqtt/ReactiveMqttConsumer.java#L192-L214)

### 5.3 消费处理流水线

核心在 [`MqttConsumePipeline`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/pipeline/MqttConsumePipeline.java#L162-L188)。

运行流程：

1. `source.messages()` 取得 MQTT envelope。
2. `onBackpressureBuffer` 做管道背压缓冲。
3. `publishOn(Schedulers.parallel())` 把处理切到并行调度器。
4. 根据 deviceId 哈希分 lane，避免无限 `groupBy(deviceId)` 造成设备组饥饿。
5. 每个 lane 内 `concatMap` 顺序处理消息。

单条消息处理在 [`processEnvelope()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/pipeline/MqttConsumePipeline.java#L197-L227)：

- 先解析 envelope。
- 再按策略生成持久化指令。
- 写入 TDengine。
- 成功后 ACK。
- 失败时记录结果并 ACK，避免消息阻塞。

### 5.4 解析模型

[`HubMessageParser`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/parser/HubMessageParser.java#L20-L39) 做两件事：

- 根据 topic 判断消息类型：telemetry / params_set / params_ack。
- 用 Jackson 反序列化到强类型 payload，且关闭未知字段失败，这让协议能平滑扩展。

### 5.5 告警、状态、摘要与入库策略

[`applyPersistencePolicy()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/pipeline/MqttConsumePipeline.java#L274-L314) 是 Data Hub 的核心价值点之一。

它不是简单“收到就写”：

- 所有消息都会进入告警规则引擎。
- 所有消息会更新设备在线状态。
- telemetry 会经过写入过滤器，稳定重复数据可跳过原始写入，但仍可产生摘要。
- params/set 和 params/ack 会刷新摘要并清空过滤器状态，保证参数变化前后可分段分析。

遥测写入过滤器在 [`TelemetryWriteFilter`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/pipeline/TelemetryWriteFilter.java#L46-L101)，会根据存储规则判断：

- 首条样本必须保存。
- 到达 heartbeat 间隔必须保存。
- 关键字段变化必须保存，例如 run id、控制周期、饱和状态、传感器状态、控制模式、目标温度、误差、PWM、PID 参数等。
- 否则可跳过稳定重复点，降低时序库压力。

### 5.6 告警规则引擎

告警规则在 [`AlarmRuleEngineService`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/alarm/AlarmRuleEngineService.java#L46-L75)。

主要输入：

- telemetry：判断越界、传感器无效、高饱和、安全故障、控制周期偏差等。
- params_ack：失败 ACK 会触发参数应用失败告警。
- device status：设备离线会触发离线告警。

告警条件在 [`onTelemetry()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/alarm/AlarmRuleEngineService.java#L99-L234)，状态机在 [`processRuleSignal()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/alarm/AlarmRuleEngineService.java#L237-L320)。状态机支持 pending active / active / pending clear，避免瞬时抖动导致告警频繁闪烁。

### 5.7 TDengine 写入

写入分发在 [`TdengineEnvelopeWriter`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/storage/TdengineEnvelopeWriter.java#L28-L39)。

REST writer 在 [`TdengineRestWriter`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/storage/TdengineRestWriter.java#L71-L136) 初始化 HTTP client、认证、批量遥测写入通道。

重要写入方法：

- telemetry：[`writeTelemetry()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/storage/TdengineRestWriter.java#L138-L160)
- summary：[`writeTelemetrySummary()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/storage/TdengineRestWriter.java#L163-L218)
- params_set：[`writeParameterSet()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/storage/TdengineRestWriter.java#L220-L247)
- params_ack：[`writeParameterAck()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/storage/TdengineRestWriter.java#L249-L286)
- device_status：[`writeDeviceStatus()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/storage/TdengineRestWriter.java#L288-L310)
- alarm_events：[`writeAlarmFact()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/storage/TdengineRestWriter.java#L312-L338)

答辩说法：

> Data Hub 不是普通 MQTT 转储脚本，而是一个有背压、有状态、有告警、有摘要、有可观测指标的 ingestion service。它把设备消息变成可检索、可追溯、可用于 AI 评估的事实数据。

## 6. HMI 后端层：控制平面与 AI 工作流

### 6.1 FastAPI 入口

[`hmi/backend/app/main.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/main.py#L15-L54) 创建 FastAPI app：

- 配置 CORS。
- 启动时可自动迁移数据库和 seed 初始数据。
- 注册 auth、users、devices、alarms、storage_rules、history、stream、ops 路由。

### 6.2 数据模型

SQLAlchemy 模型在 [`entities.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/models/entities.py#L12-L188)。

核心表：

- `users`, `roles`, `user_roles`, `user_devices`：认证、角色和设备权限。
- `devices`：设备基础信息和当前状态。
- `device_parameters`：PID 参数、目标带、饱和阈值、采样周期等。
- `device_alarms`, `alarm_rules`：告警实例和规则。
- `storage_rules`：控制 Data Hub 原始数据保留策略。

AI 与学习闭环相关表在 [`entities.py` 192-337 行](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/models/entities.py#L192-L337)：

- `ai_recommendations`：AI 推荐历史。
- `control_actions`：人工或 AI 参数应用动作。
- `control_action_eval_jobs`：应用后评估任务。
- `control_action_feedback_samples`：用于后续训练的反馈样本。

### 6.3 认证、角色和设备权限

登录接口在 [`auth.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/auth.py#L15-L33)：

- 用户可用 username 或 email 登录。
- 密码通过 hash 校验。
- 成功后签发 JWT。
- `/auth/me` 返回用户和角色。

权限依赖在 [`deps.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/deps.py#L22-L84)：

- `get_current_user()` 解码 JWT。
- `require_roles()` 控制 admin/operator/viewer。
- `require_device_access()` 控制非 admin 用户只能访问自己绑定的设备。

### 6.4 设备、历史和控制评估 API

设备列表和详情：

- 列表：[`list_devices()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1290-L1308)
- 管理分页：[`list_devices_paginated()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1311-L1339)
- 详情：[`get_device()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1342-L1352)

时序数据读取：

- 设备曲线：[`get_metrics()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1414-L1463)
- 窗口统计：[`get_metric_window_stats()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1466-L1512)
- 控制性能评估：[`get_control_eval()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1515-L1624)

这些接口优先读 TDengine，失败或无数据时可回退到 PostgreSQL demo/历史数据。TDengine REST 客户端在 [`tdengine_client.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/tdengine_client.py#L27-L115)。

### 6.5 参数更新与 MQTT 下发

手动更新参数接口在 [`update_parameters()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1644-L1706)：

1. 检查用户设备权限。
2. 记录更新前参数。
3. 更新目标温度或 PID 参数。
4. 调用 `_dispatch_and_confirm_parameter_update()` 通过 MQTT 下发并等待 ACK。
5. 记录一次 `ControlAction`，为应用后评估和学习闭环做准备。

MQTT 发布器在 [`mqtt_publisher.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/mqtt_publisher.py#L29-L125)：

- `publish_params_set()` 构造 `params/set` payload。
- `publish_raw()` 连接 broker、发布消息、等待 publish 完成。

ACK 等待逻辑在 [`_wait_latest_params_ack()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L168-L197) 和 [`_wait_latest_params_ack_relaxed()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L200-L277)，用于处理 Data Hub 入库延迟或时钟偏移。

### 6.6 实时 WebSocket

WebSocket 在 [`stream.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/stream.py#L110-L139)：

- 通过 query token 解码用户。
- 每个周期查询用户可访问设备。
- 优先从 TDengine 最新 telemetry 填充实时温度、目标温度、PWM 和告警状态。
- 发送 `device_snapshot` 给前端。

### 6.7 AI 推荐生成、预览、应用、验证

推荐生成接口在 [`generate_ai_recommendation()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1832-L1959)：

1. 加载设备当前状态和参数。
2. 从历史窗口构造 AI 输入。
3. 调用 AI 运行时或本地推荐逻辑。
4. 生成 fingerprint，避免短时间重复推荐刷屏。
5. 将推荐写入 `ai_recommendations`，并返回前端。

预览接口在 [`preview_ai_recommendation()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L2194-L2257)，用当前参数和推荐参数跑一阶热模型仿真。

应用接口在 [`apply_ai_recommendation()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1984-L2191)：

- 解析推荐中的 PID 参数。
- 如果最近 ACK 已经匹配推荐，走 ACK shortcut，避免重复下发。
- 如果当前运行参数已经匹配，走幂等路径。
- 否则更新参数，通过 MQTT 下发，并记录 `ControlAction`。

实际效果评估接口从 [`evaluate_ai_recommendation_actual()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L2260-L2285) 开始，后续会读取应用后的 telemetry，与预览或应用前基线比较。

## 7. AI 决策层：可解释推荐而不是黑盒控制

### 7.1 推荐服务总流程

[`RecommendationService.generate()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/recommendation_service.py#L35-L76) 是本地 AI 推荐主流程：

```text
历史窗口
-> extract_features
-> classify_problem
-> build_recommendation
-> 输出问题类型、置信度、风险、当前参数、推荐参数、证据
```

它的优点是可解释：推荐结果里保存了 `mean_error`, `error_std`, `zero_crossings`, `in_band_ratio`, `overshoot_pct`, `saturation_ratio` 等证据字段。

### 7.2 特征提取

[`extract_features()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/feature_extractor.py#L37-L80) 从历史点计算：

- 平均误差、平均绝对误差、误差标准差。
- 温度波动范围。
- PWM 平均值和最大值。
- 误差过零次数，用于判断振荡。
- 在目标带内比例。
- 超调百分比。
- 稳定时间。
- 饱和比例。

### 7.3 问题分类

[`classify_problem()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/problem_classifier.py#L63-L69) 根据规则输出主问题和次问题。

规则位置：

- 饱和：[`7-12 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/problem_classifier.py#L7-L12)
- 振荡：[`13-14 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/problem_classifier.py#L13-L14)
- 超调：[`15-16 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/problem_classifier.py#L15-L16)
- 稳态误差：[`17-18 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/problem_classifier.py#L17-L18)
- 响应慢：[`19-21 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/problem_classifier.py#L19-L21)

### 7.4 参数调整策略

[`tuning_engine.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/tuning_engine.py#L18-L91) 根据问题类型给出 PID 参数变化：

- 响应慢：增加 `kp` 和 `ki`。
- 稳态误差：增加 `ki`。
- 超调高：降低 `kp`、降低 `ki`、增加 `kd`。
- 振荡：降低 `kp`、降低 `ki`、增加 `kd`。
- 饱和受限：小幅增加 `kp`，并标记高风险。
- 非正常推荐都需要人工确认。

### 7.5 预览仿真

预览仿真在 [`RecommendationPreviewSimulator.run()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/preview_simulator.py#L152-L208)：

- 用 baseline 参数和 recommended 参数分别模拟曲线。
- 计算 in-band ratio、overshoot、settling、temp swing、mean absolute error、saturation ratio。
- 输出 improvement，且方向统一为“正数代表改善”。

预览 PID 控制器在 [`PreviewPidController.update()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/preview_simulator.py#L85-L149)，逻辑与设备端 `PiController` 对齐。热模型在 [`_simulate_curve()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/preview_simulator.py#L211-L252)，使用一阶惯性：

```text
dT/dt = heating_gain * u - cooling_coeff * (T - ambient)
```

答辩说法：

> AI 层没有直接越权控制设备，而是输出可解释建议，并通过预览仿真和人工确认降低风险。真正应用仍走统一的 MQTT `params/set` 和设备 ACK 流程。

## 8. HMI 前端层：操作员如何使用系统

### 8.1 路由和权限页面

前端路由在 [`router.tsx`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/routes/router.tsx#L34-L52)：

- `/`：概览，自动进入第一个设备。
- `/devices/:id`：设备详情。
- `/ai`：应用后验证和 AI 历史。
- `/alarms`：告警中心。
- `/history`：历史摘要。
- `/ops`, `/storage-rules`, `/users`：admin 才能访问。

登录状态和角色判断在 [`auth.tsx`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/app/auth.tsx#L16-L66)。

### 8.2 API 封装

[`api.ts`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/lib/api.ts#L62-L92) 做统一请求：

- 从 `localStorage` 读取 JWT。
- 加 Authorization header。
- 设置请求超时。
- 非 2xx 转成异常。

业务 API 集中在 [`api` 对象](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/lib/api.ts#L94-L253)，包括设备、指标、参数、AI 推荐、预览、实际评估、用户、告警等。

### 8.3 实时数据 hook

[`useDevices()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/routes/use-data.ts#L33-L94)：

- 初次通过 REST 加载设备列表。
- 建立 WebSocket，收到 `device_snapshot` 后更新设备状态。
- 断线后 2 秒重连。

[`useDeviceDetail()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/routes/use-data.ts#L96-L205)：

- 并发加载设备详情、metrics、parameters、alarms、AI recommendation。
- WebSocket 来新快照时追加一条图表 metric，最多保留 1000 个点。
- 对页面暴露 `updateParameters`, `acknowledgeAlarm`, `applyAiRecommendation`。

### 8.4 页面结构

全局布局在 [`layout-shell.tsx`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/components/layout-shell.tsx#L8-L65)：顶部状态栏 + 左侧导航 + 主内容区。

主要页面：

- 设备详情：[`device-detail-page.tsx`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/pages/device-detail-page.tsx#L77-L130)，承担实时曲线、参数编辑、AI 生成/预览/应用。
- AI 页面：[`ai-page.tsx`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/pages/ai-page.tsx#L1-L80)，聚合 AI 推荐历史和应用后验证。
- 告警页：[`alarms-page.tsx`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/pages/alarms-page.tsx#L13-L67)，展示活跃/历史告警并编辑规则。
- 历史页：[`history-page.tsx`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/pages/history-page.tsx#L11-L71)，查看摘要和详情。
- 运维页：[`ops-page.tsx`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/pages/ops-page.tsx#L14-L143)，展示 Data Hub、运行时、AI 可观测性、模型生命周期。

## 9. AI 决策与离线训练详解

这一层要按论文第 6 章的边界来讲：AI 是 decision support，不是 autonomous control。边缘端闭环控制仍由设备端 PI/PID 控制器执行；AI 只根据历史 telemetry 诊断控制问题、生成保守 PID 参数建议、做预览仿真、等待操作员确认，并在应用后沉淀反馈样本。

### 9.1 在线 AI 决策链路

在线决策入口有两种形态：

- HMI 后端接口 [`generate_ai_recommendation()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1832-L1959) 从设备状态、参数和历史窗口构造输入。
- 本地推荐服务 [`RecommendationService.generate()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/recommendation_service.py#L35-L76) 执行“特征 -> 分类 -> 调参”基础链路。

核心流程：

```text
历史 telemetry + 当前 PID 参数
-> feature_extractor 计算控制特征
-> problem_classifier 规则分类问题类型
-> tuning_engine 根据问题类型生成 rule_center 推荐
-> recommendation_orchestrator 可选加载模型排序候选
-> preview_simulator 对候选参数做一阶热模型预览
-> 保存 ai_recommendations 和 runtime_decision 元数据
-> 操作员确认后走 MQTT params/set + params/ack
-> control_action_learning 延迟评估实际效果
```

三层编排写在 [`RecommendationOrchestrator`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/recommendation_orchestrator.py#L22-L27)：

1. `rule diagnosis`：用规则分类控制问题。
2. `rule base tuning`：用 PID 工程经验生成中心候选 `rule_center`。
3. `optional model-based candidate ranking`：如果训练好的模型存在，再对多个候选排序；模型缺失或加载失败时自动回退到 `rule_center`。

为什么这样设计：

- 先规则、后模型：规则可解释、容易答辩、适合小数据阶段；模型只做辅助排序，避免“黑盒直接改 PID”。
- 不用端到端深度学习：本项目样本规模小、真实硬件数据有限，深度模型需要大量标注和分布覆盖，且很难解释为什么推荐某组 PID。
- 不用强化学习直接控制：强化学习需要大量在线试错，温控系统存在安全边界和设备风险；论文强调 human-in-the-loop，所以不能让算法绕过人工确认直接探索。
- 不直接回归 `kp/ki/kd`：直接回归参数很难保证安全、有界和可解释。本项目先用规则生成候选，再用分类模型判断“哪个候选更可能改善、预览误差更小”。

### 9.2 特征提取：AI 判断依据是什么

在线特征在 [`feature_extractor.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/feature_extractor.py#L37-L80) 中计算，离线训练使用同类指标，保证训练和运行时语义一致。

关键特征：

| 特征 | 控制含义 | 用途 |
|---|---|---|
| `mean_error`, `mean_abs_error` | 平均误差和平均绝对误差 | 判断是否长期偏离目标 |
| `error_std`, `temp_swing` | 误差波动和温度摆幅 | 判断是否振荡或控制不稳 |
| `zero_crossings` | 误差穿越 0 的次数 | 高频穿越通常对应振荡 |
| `in_band_ratio` | 落在目标带内的比例 | 衡量控制质量 |
| `overshoot_pct` | 超调比例 | 判断是否响应过猛 |
| `settling_sec` | 进入目标带并保持的时间 | 衡量调节速度 |
| `saturation_ratio`, `pwm_max` | PWM 饱和情况 | 判断执行器是否长期顶满 |

答辩时可以说：

> AI 没有直接看一条瞬时温度就给建议，而是把一段历史窗口压缩成控制性能特征。这些特征都是控制工程里能解释的指标，比如误差、超调、振荡、饱和和稳定时间。

### 9.3 问题分类：用了什么算法，为什么用规则

在线分类目前使用规则分类器，代码在 [`problem_classifier.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/problem_classifier.py#L7-L69)。

规则示例：

- 饱和受限：[`saturation_ratio` 和 `pwm_max`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/problem_classifier.py#L7-L12)
- 振荡：[`zero_crossings` + `error_std`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/problem_classifier.py#L13-L14)
- 超调：[`overshoot_pct`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/problem_classifier.py#L15-L16)
- 稳态误差：[`in_band_ratio` + `mean_abs_error`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/problem_classifier.py#L17-L18)
- 响应慢：[`in_band_ratio` + `settling_sec`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/problem_classifier.py#L19-L21)

为什么用规则分类作为在线主路径：

- 控制问题类别少，且每类都有明确物理含义。
- 小数据阶段规则比复杂模型更稳定，避免训练集偏差造成危险建议。
- 规则输出可解释证据，适合 HMI 展示和论文答辩。
- 规则失败风险可控：最多给出保守建议，不会绕过设备端安全限值。

离线的 `train_problem_classifier.py` 仍训练了两个模型：Logistic Regression 和 Random Forest。特征列在 [`FEATURE_CANDIDATES`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/ai/scripts/train_problem_classifier.py#L27-L43)，模型定义在 [`train_baseline_model()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/ai/scripts/train_problem_classifier.py#L157-L179) 和 [`train_tree_model()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/ai/scripts/train_problem_classifier.py#L182-L204)。这部分用于实验和后续扩展，不是当前最可信的运行时安全边界。

算法选择理由：

| 算法 | 为什么用 | 为什么不是唯一依赖 |
|---|---|---|
| Logistic Regression | 线性、可解释、训练快，能作为基线模型；系数可以反映特征方向 | 控制问题可能有非线性边界，单独使用可能欠拟合 |
| Random Forest | 能捕捉非线性和特征交互，对特征缩放不敏感，并输出 feature importance | 小数据时可能过拟合，所以需要验证指标和晋级门槛 |
| 规则分类器 | 可解释、稳定、安全边界清楚，适合在线主路径 | 规则阈值需要经验，长期可用反馈数据校准 |

### 9.4 参数推荐：用了什么调参策略

PID 推荐策略在 [`tuning_engine.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/tuning_engine.py#L18-L91)。

调参逻辑是工程启发式，不是黑盒生成：

| 问题类型 | 参数方向 | 控制含义 |
|---|---|---|
| `slow_response` | 增加 `kp` 和 `ki` | 加强响应速度和误差消除 |
| `steady_state_error` | 增加 `ki` | 用积分项消除长期静差 |
| `overshoot_high` | 降低 `kp/ki`，增加 `kd` | 减少过冲，加强阻尼 |
| `oscillation` | 降低 `kp/ki`，增加 `kd` | 降低振荡倾向 |
| `saturation_limited` | 小幅调整并标高风险 | 执行器顶满时不能激进加参数 |

为什么不让模型直接输出 PID：

- PID 参数必须非负、有边界、有物理含义，直接回归容易产生危险值。
- 老师追问时，规则调参能解释“为什么 `ki` 增加/为什么 `kp` 降低”。
- 设备端仍会做参数范围校验，形成双层保护：AI 保守建议 + edge validator 拒绝越界。

### 9.5 候选排序：机器学习到底用在哪里

可选模型排序在 [`RecommendationRanker`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/recommendation_ranker.py#L53-L99) 中。它不生成全新 PID，而是在规则中心候选附近生成少量可解释候选。

候选生成在 [`generate_candidates()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/recommendation_ranker.py#L112-L316)，包括：

- `rule_center`：规则推荐本身。
- `conservative`：更保守的调整。
- `aggressive`：更积极的调整，但仍有边界。
- `overshoot_guard`：偏向抑制超调。
- `settling_focus`：偏向更快进入稳定区。
- `baseline_hold`：不改参数，用作 no-change 参照。

每个候选先跑预览仿真，生成预览指标：[`_simulate_preview_summary()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/recommendation_ranker.py#L318-L345)。然后把候选参数、推荐时证据和预览摘要拼成模型特征：[`_build_features()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/recommendation_ranker.py#L347-L381)。

排序使用两个分类模型：

1. `Recommendation Success Predictor`：预测候选应用后是 `improved / unchanged / worse`。
2. `Preview Gap Predictor`：预测预览和实际效果差距是 `low / medium / high`。

评分公式在 [`_compute_total_score()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/recommendation_ranker.py#L391-L416)：

```text
success_score = P(improved) - 0.5 * P(unchanged) - 1.0 * P(worse)
gap_score     = P(low)      - 0.5 * P(medium)    - 1.0 * P(high)
total_score   = 0.65 * success_score + 0.35 * gap_score
```

为什么这样打分：

- `worse` 和 `high gap` 被强惩罚，体现安全优先。
- `unchanged` 和 `medium gap` 不是灾难，但也不是好结果，所以给半惩罚。
- `success` 权重 0.65，高于 preview gap 的 0.35，因为最终目标是实际改善；但预览偏差仍会影响排序，避免选中“仿真看着好、实际不可靠”的候选。

模型加载和回退在 [`RecommendationOrchestrator._load_ranker()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/recommendation_orchestrator.py#L54-L89) 和 [`generate_ranked_recommendation()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/recommendation_orchestrator.py#L99-L201)。如果模型不存在、joblib 加载失败或候选评分异常，最终仍使用 `rule_center`。

### 9.6 离线训练链路一：TDengine 遥测到问题分类样本

离线 ML 目录的作用是把运行数据转成训练数据，不直接参与实时控制。配置集中在 [`training_data.yaml`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/configs/training_data.yaml#L1-L90)。

步骤 1：从 TDengine 导出原始表。

- 脚本：[`export_tdengine_data.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/export_tdengine_data.py#L188-L251)
- 导出表：`telemetry`, `params_ack`, `params_set`, `telemetry_summary`, `alarm_events`
- 关键实现：构造 TDengine REST SQL，支持 device 和时间范围过滤：[`build_where_clause()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/export_tdengine_data.py#L80-L98)

命令：

```bash
python ml/scripts/export_tdengine_data.py \
  --config ml/configs/training_data.yaml \
  --device-id edge-node-001 \
  --start-ms 1712200000000 \
  --end-ms 1712203600000
```

步骤 2：构造滑动窗口。

- 脚本：[`build_training_windows.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/build_training_windows.py#L213-L267)
- 默认 30 分钟窗口、5 分钟步长、至少 30 个点：[`resolve_window_cfg()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/build_training_windows.py#L270-L312)
- 清洗规则：过滤 `sensor_valid=false` 和 `fault_latched=true`，删除缺失关键字段：[`clean_telemetry()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/build_training_windows.py#L73-L103)
- 稳定性规则：一个窗口内 `control_mode/kp/ki/kd` 不能明显变化：[`stable_params()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/build_training_windows.py#L106-L122)
- 采样质量规则：最大间隔、平均采样周期、采样比例：[`is_window_sampling_healthy()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/build_training_windows.py#L160-L210)

命令：

```bash
python ml/scripts/build_training_windows.py --config ml/configs/training_data.yaml
```

为什么用滑动窗口：

- 控制质量是时间段概念，不是单点概念；一个点无法判断超调、稳定时间或振荡。
- 30 分钟窗口能覆盖温控响应过程，5 分钟步长能增加样本数量并保留时序连续性。
- 参数稳定性过滤能避免“窗口中途换 PID”导致标签混乱。

步骤 3：提取训练特征。

- 脚本：[`extract_features.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/extract_features.py#L117-L304)
- 过零次数：[`compute_zero_crossings()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/extract_features.py#L55-L65)
- 稳定时间：[`compute_settling_sec()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/extract_features.py#L73-L91)
- 输出字段包含误差、PWM、超调、饱和、状态比例等：[`extract_window_features()` 返回值](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/extract_features.py#L261-L304)

命令：

```bash
python ml/scripts/extract_features.py --config ml/configs/training_data.yaml
```

步骤 4：生成伪标签。

- 脚本：[`label_samples.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/label_samples.py#L124-L161)
- 标签规则：[`compute_problem_flags()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/label_samples.py#L74-L99)
- 多问题优先级：[`derive_problem_labels()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/label_samples.py#L102-L116)

命令：

```bash
python ml/scripts/label_samples.py --config ml/configs/training_data.yaml
```

重要答辩边界：

> 这里的标签是 rule-based pseudo label，不是人工标注的绝对 ground truth。它的价值是把大量 telemetry 转成可实验的数据集，便于训练基线模型和验证特征有效性；生产运行时仍以规则和人工确认为安全边界。

### 9.7 离线训练链路二：控制动作反馈到推荐排序模型

第二条训练链路来自真实应用后的反馈，而不是单纯遥测窗口。这更接近论文里“推荐 -> 应用 -> ACK -> 应用后验证 -> 学习样本”的闭环。

应用参数后，后端会创建 `ControlAction` 和 `ControlActionEvalJob`。逻辑在 [`create_action_and_eval_job()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/control_action_learning.py#L353-L424)：

- 记录应用前后 PID、目标温度、来源、操作者。
- 根据问题类型选择观察窗口：振荡/超调 12 分钟，稳态误差 18 分钟，慢响应/饱和 25 分钟，其他 AI 默认 15 分钟，手动默认 20 分钟：[`choose_observation_window_minutes()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/control_action_learning.py#L239-L266)
- 延迟到观察窗口结束后再评估，避免刚应用就误判“数据不足”：[`406-408 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/control_action_learning.py#L406-L408)

评估 worker 在 [`run_control_action_feedback_worker.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/scripts/run_control_action_feedback_worker.py#L118-L170)：

- 找到到期的 pending eval jobs。
- 调用 `evaluate_control_action()`。
- 数据未成熟则 reschedule，重试耗尽或冲突则标记 insufficient。

命令：

```bash
hmi/backend/.venv/bin/python hmi/backend/scripts/run_control_action_feedback_worker.py --batch-size 50
```

应用后评估在 [`evaluate_control_action()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/control_action_learning.py#L522-L836)：

1. 读取应用后的 telemetry：[`562-596 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/control_action_learning.py#L562-L596)
2. 计算实际控制指标：[`605-615 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/control_action_learning.py#L605-L615)
3. 读取应用前 baseline 窗口：[`617-649 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/control_action_learning.py#L617-L649)
4. 读取 AI 推荐里的预览指标和 runtime decision：[`667-695 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/control_action_learning.py#L667-L695)
5. 比较 actual vs baseline 和 actual vs preview：[`709-715 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/control_action_learning.py#L709-L715)
6. 过滤冲突情况，例如观察窗口内又改参数、设备离线太久、目标温度中途变化：[`717-742 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/control_action_learning.py#L717-L742)
7. 生成 `actual_effect_label` 和 `preview_gap_label`，并持久化反馈样本：[`744-816 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/control_action_learning.py#L744-L816)

反馈样本字段写入在 [`_persist_feedback_sample()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/control_action_learning.py#L426-L520)，包含：

- 应用前后 PID 和 delta。
- 推荐时的证据特征。
- runtime decision summary，例如 top candidate 和分数。
- preview metrics 和 actual metrics。
- `actual_effect_label`：`improved / unchanged / worse`
- `preview_gap_label`：`low / medium / high`
- `is_training_eligible` 和排除原因。

导出反馈数据有两个脚本：

- 原始控制动作反馈表导出：[`export_control_action_feedback_samples.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/ml/scripts/export_control_action_feedback_samples.py#L91-L112)
- 推荐排序训练集导出：[`export_recommendation_feedback_dataset.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/ai/scripts/export_recommendation_feedback_dataset.py#L82-L128)

命令：

```bash
python ml/scripts/export_control_action_feedback_samples.py
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/export_recommendation_feedback_dataset.py --only-usable
```

### 9.8 训练 recommendation_success 和 preview_gap 模型

`recommendation_success` 训练脚本在 [`train_recommendation_success_model.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/ai/scripts/train_recommendation_success_model.py#L1-L381)：

- 标签：`effect_outcome`
- 类别：`improved`, `unchanged`, `worse`：[`ALLOWED_LABELS`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/ai/scripts/train_recommendation_success_model.py#L17-L20)
- 只用 `feedback_usable_for_training=true` 的样本：[`load_training_data()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/ai/scripts/train_recommendation_success_model.py#L72-L94)
- 特征只包含推荐时可获得的信息和预览摘要：[`FEATURE_COLUMNS`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/ai/scripts/train_recommendation_success_model.py#L21-L52)
- 同时训练 Logistic Regression 和 Random Forest：[`351-355 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/ai/scripts/train_recommendation_success_model.py#L351-L355)

`preview_gap` 训练脚本在 [`train_preview_gap_model.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/ai/scripts/train_preview_gap_model.py#L1-L379)：

- 标签：`preview_gap_level`
- 类别：`low`, `medium`, `high`：[`ALLOWED_LABELS`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/ai/scripts/train_preview_gap_model.py#L17-L20)
- 明确排除泄漏字段，例如实际发生后才知道的 preview-vs-actual gap 数值：[`21-24 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/ai/scripts/train_preview_gap_model.py#L21-L24)
- 同样训练 Logistic Regression 和 Random Forest：[`341-345 行`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/ai/scripts/train_preview_gap_model.py#L341-L345)

命令：

```bash
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/train_recommendation_success_model.py
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/train_preview_gap_model.py
```

为什么是分类模型而不是回归模型：

- 反馈标签天然是工程等级：改善、无明显变化、变差；预览差距也是低、中、高。
- 分类概率可以直接进入候选排序公式，便于解释 `P(worse)` 为什么被惩罚。
- 回归一个连续分数需要更稳定的大样本和更严密的标定，否则答辩时很难说明阈值来源。

为什么保留 Logistic Regression 和 Random Forest 两类：

- Logistic Regression 是可解释 baseline，老师问“模型根据什么判断”时可以看系数和 feature importance。
- Random Forest 更适合捕捉“高超调 + 高饱和 + 参数 delta”这类非线性交互。
- 两者一起训练并比较，避免只拿一个模型讲故事；最终上线还要经过生命周期 gate。

### 9.9 模型生命周期：为什么离线训练不会随便上线

模型生命周期服务在 [`model_lifecycle_service.py`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/model_lifecycle_service.py#L54-L60)，管理三个目录：

- `artifacts/candidates`：新训练出来的候选模型。
- `artifacts/active`：运行时可加载模型。
- `artifacts/archive`：历史 active 模型归档。

它管理两个模型家族：[`FAMILIES`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/model_lifecycle_service.py#L30-L47)

- `recommendation_success`：危险标签是 `worse`。
- `preview_gap`：危险标签是 `high`。

训练集构造在 [`_build_training_dataset()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/model_lifecycle_service.py#L104-L152)，训练脚本调用在 [`_run_train_script()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/model_lifecycle_service.py#L154-L165)。

上线 gate 在 [`_gate()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/model_lifecycle_service.py#L275-L369)，检查：

- 验证集样本数不能太小。
- `macro_f1` 不能比 active 模型明显退化。
- 危险类召回不能明显退化，例如 `worse` 不能更容易漏判。
- 危险误分类率不能变差，例如把 `worse` 判成 `improved` 是严重问题。
- 如果是第一次晋级，也要满足危险类召回下限。

晋级逻辑在 [`_archive_and_promote()`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/model_lifecycle_service.py#L371-L413)：先归档旧 active，再删除同家族旧文件，只复制获胜 variant。这保证运行时每个模型家族只有一个可选 active variant。

答辩时可以说：

> 离线训练不会自动把模型塞进在线决策。新模型必须经过样本数、宏平均 F1、危险类召回和危险误分类率 gate；即使 active 模型不存在，第一次上线也要过安全阈值。运行时模型加载失败还会回退规则推荐。

### 9.10 AI 训练与决策命令清单

```bash
# 1. 遥测伪标签数据集
python ml/scripts/export_tdengine_data.py --config ml/configs/training_data.yaml
python ml/scripts/build_training_windows.py --config ml/configs/training_data.yaml
python ml/scripts/extract_features.py --config ml/configs/training_data.yaml
python ml/scripts/label_samples.py --config ml/configs/training_data.yaml

# 2. 问题分类模型实验
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/train_problem_classifier.py

# 3. 控制动作应用后评估
hmi/backend/.venv/bin/python hmi/backend/scripts/run_control_action_feedback_worker.py --batch-size 50

# 4. 推荐反馈数据集
python ml/scripts/export_control_action_feedback_samples.py
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/export_recommendation_feedback_dataset.py --only-usable

# 5. 推荐成功率和预览差距模型
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/train_recommendation_success_model.py
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/train_preview_gap_model.py

# 6. 离线候选排序实验
hmi/backend/.venv/bin/python hmi/backend/ai/scripts/rank_candidate_recommendations.py
```

### 9.11 AI 部分答辩高频问答

老师问：你用了什么 AI 算法？

> 在线主路径是规则诊断 + PID 工程启发式调参 + 可选监督学习候选排序。监督学习部分用了 Logistic Regression 作为可解释 baseline，用 Random Forest 捕捉非线性特征交互。它们不是直接控制器，而是对候选参数做成功概率和预览误差风险评估。

老师问：为什么不用深度学习？

> 因为本项目的数据规模、标注质量和安全要求不适合深度学习。温控参数推荐需要可解释、安全、有界，深度模型虽然复杂，但在小数据下容易过拟合，也难解释具体 PID 调整原因。论文目标是实现可验证的边缘温控平台和闭环决策支持，不是追求模型复杂度。

老师问：为什么不用强化学习？

> 强化学习需要试错探索，但温控系统有安全边界，不能为了学习让设备在线尝试危险参数。本项目采用 human-in-the-loop，AI 给建议，操作员确认，设备端仍保留参数校验和过温保护。

老师问：离线训练怎么避免数据泄漏？

> 训练 `preview_gap` 时只使用推荐时可获得的 baseline 参数、推荐参数、推荐证据和预览摘要，明确排除了实际发生后才知道的 preview-vs-actual gap 字段。代码在 `train_preview_gap_model.py` 的特征定义处有注释说明。

老师问：AI 推荐失败怎么办？

> 模型排序是增强，不是必需。`RecommendationOrchestrator` 加载模型失败、模型不存在或候选排序异常时，会保留规则推荐 `rule_center`。这保证系统不会因为模型文件问题影响基本推荐能力。

答辩总结句：

> AI 层的核心价值不是替代控制器，而是把 telemetry 变成可解释诊断，把 PID 调参经验变成可审计建议，再通过应用后验证把真实效果沉淀为训练样本。这样系统既有工程安全边界，也有后续数据驱动优化的路径。

## 10. 最重要的三条答辩链路

### 链路 A：设备实时遥测如何显示到前端

```text
EdgeTemperatureApp::run_control_tick
-> TelemetryBuilder::to_json
-> MqttGateway::publish_telemetry
-> ReactiveMqttConsumer::onMessage
-> HubMessageParser::parse
-> MqttConsumePipeline::applyPersistencePolicy
-> TdengineRestWriter::writeTelemetry
-> HMI backend TdengineClient.query
-> /devices/{id}/metrics 或 /stream/devices
-> frontend useDeviceDetail / useDevices
-> DeviceDetailPage 图表和状态
```

关键代码：

- 设备生成遥测：[`edge_app.cpp#L262-L267`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/app/edge_app.cpp#L262-L267)
- MQTT 消费：[`ReactiveMqttConsumer.java#L168-L181`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/mqtt/ReactiveMqttConsumer.java#L168-L181)
- 管道入库：[`MqttConsumePipeline.java#L197-L227`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/pipeline/MqttConsumePipeline.java#L197-L227)
- 后端查询 metrics：[`devices.py#L1414-L1457`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1414-L1457)
- 前端实时 hook：[`use-data.ts#L129-L189`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/routes/use-data.ts#L129-L189)

### 链路 B：人工修改 PID 参数如何真正到设备

```text
DeviceDetailPage 点击保存
-> api.updateParameters
-> PUT /devices/{id}/parameters
-> MqttPublisher.publish_params_set
-> edge/temperature/<device_id>/params/set
-> MqttGateway.handle_mqtt_message
-> ParamUpdateHandler.on_params_message
-> RuntimeConfigStore.apply_now
-> MqttGateway.publish_ack_json
-> Data Hub 持久化 params_ack
-> HMI backend 等待 ACK
-> 记录 ControlAction
```

关键代码：

- 前端 API：[`api.ts#L171-L176`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/frontend/src/lib/api.ts#L171-L176)
- 后端接口：[`devices.py#L1644-L1706`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1644-L1706)
- MQTT 发布：[`mqtt_publisher.py#L29-L55`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/mqtt_publisher.py#L29-L55)
- 设备接收：[`mqtt_gateway.cpp#L32-L53`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/comms/mqtt/mqtt_gateway.cpp#L32-L53)
- 参数应用：[`param_update_handler.cpp#L22-L72`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/comms/mqtt/param_update_handler.cpp#L22-L72)

### 链路 C：AI 推荐如何闭环验证

```text
历史 telemetry
-> RecommendationService.extract/classify/tune
-> ai_recommendations 保存推荐
-> preview_simulator 生成预览曲线
-> apply_ai_recommendation 走 MQTT params/set
-> 设备 ACK
-> ControlAction / EvalJob
-> 后续 telemetry 实际效果评估
-> ControlActionFeedbackSample
-> 离线训练数据
```

关键代码：

- 推荐生成：[`recommendation_service.py#L35-L76`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/recommendation_service.py#L35-L76)
- 生成接口：[`devices.py#L1832-L1959`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1832-L1959)
- 预览仿真：[`preview_simulator.py#L152-L208`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/preview_simulator.py#L152-L208)
- AI 应用：[`devices.py#L1984-L2191`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1984-L2191)
- 学习闭环：[`control_action_learning.py#L353-L407`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/control_action_learning.py#L353-L407)

## 11. 推荐辅助开源工具

这些工具可以帮你“浏览”或“可视化”代码，但不能替代上面的业务源码地图。

| 工具 | 适合做什么 | 对本项目的建议 |
|---|---|---|
| [CodeCharta](https://codecharta.com/) | 把代码库变成 3D code map，按行数、复杂度、技术债看热点。官方说明其分析和可视化可在本地完成，代码不会被上传。 | 适合用来找“大文件/高复杂度热点”，比如 `devices.py`, `device-detail-page.tsx`, `ai-page.tsx`。不适合解释业务链路。 |
| [OpenGrok](https://github.com/oracle/opengrok) | 自建源码搜索和交叉引用站，适合跨语言大仓库跳转符号定义和引用。 | 如果你想像公司内部代码搜索一样浏览仓库，可以部署它；但毕业答辩准备成本略高。 |
| GitHub 固定行号链接 | 最简单稳定，能直接打开对应代码。 | 本文档已经采用这种方式，最适合答辩和论文备注。 |

## 12. 论文追问答法

### 12.1 老师问：你的系统为什么不是普通监控系统？

论文依据：第 3 章强调它是 layered closed-loop workflow。

源码回答：

- 设备端不是只发温度，而是本地控制并发布控制上下文：[`edge_app.cpp#L203-L272`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/app/edge_app.cpp#L203-L272)
- Data Hub 不只是存温度，还存 telemetry、params_set、params_ack、summary、device_status、alarm_event：[`TdengineRestWriter.java#L138-L338`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/storage/TdengineRestWriter.java#L138-L338)
- HMI 修改参数后会走 MQTT 下发和 ACK 确认，不是前端改一个显示值：[`devices.py#L1644-L1706`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1644-L1706)

可讲答案：

> 普通监控系统通常只展示当前值；我的系统把测量、控制、上报、入库、参数下发、设备确认和应用后观察串成一个可追溯链路。也就是说，一个温度点不是孤立显示值，而是后续判断控制质量和验证参数变化的证据。

### 12.2 老师问：论文说默认 23 °C、20-60 °C 范围、65 °C 安全限值，代码在哪里？

源码回答：

- 默认目标、PID 默认值、控制周期、范围和安全限值都在 [`app_config.h#L13-L29`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/config/app_config.h#L13-L29)。
- 参数范围校验在 [`param_validator.cpp#L13-L42`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/comms/mqtt/param_validator.cpp#L13-L42)。
- 安全故障触发和输出强制为 0 在 [`edge_app.cpp#L220-L255`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/app/edge_app.cpp#L220-L255)。

可讲答案：

> 这些数值不是论文里随便写的，它们对应边缘端默认配置和参数校验。越界目标温度不会被应用；传感器无效或超过软件安全限值时，固件会锁存 fault，并强制关闭 actuator 输出。

### 12.3 老师问：Wokwi 仿真和真实硬件是什么关系？

论文依据：第 4 章明确当前验证以 simulator profile 为主，PCB、MOSFET、传感器位置和热负载仍需仪器测试。

源码回答：

- `sketch.ino` 根据 `EDGE_BUILD_SIMULATOR` 选择 Wokwi 或 real hardware 类：[`sketch.ino#L7-L41`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/sketch.ino#L7-L41)
- 仿真热模型是 `current + heating - cooling`：[`thermal_plant_model.cpp#L5-L9`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/hardware/wokwi/thermal_plant_model.cpp#L5-L9)
- 真实硬件接口预留在 `hardware/real` 目录。

可讲答案：

> Wokwi 主要验证软件闭环、消息链路和参数流程。因为 Wokwi 的虚拟 heater 不会真实加热 DS18B20，所以我用虚拟热模型作为受控对象，同时仍保留传感器读数和真实硬件 profile。论文没有夸大成最终硬件实测，真实 PCB 还需要示波器、万用表、外部温度计和负载测试。

### 12.4 老师问：Data Hub 的可靠性体现在哪里？

论文依据：第 5.1 节说它是 bounded asynchronous processing flow，不是无限队列。

源码回答：

- MQTT 入口队列有界：[`ReactiveMqttConsumer.java#L43-L52`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/mqtt/ReactiveMqttConsumer.java#L43-L52)
- 管道有 backpressure buffer、prefetch、parallel scheduler 和 device lane：[`MqttConsumePipeline.java#L162-L188`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/pipeline/MqttConsumePipeline.java#L162-L188)
- 处理失败会记录 outcome 并 ACK，避免 QoS1 inflight 卡死：[`MqttConsumePipeline.java#L197-L227`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/pipeline/MqttConsumePipeline.java#L197-L227)

可讲答案：

> Data Hub 的重点是连续消息处理的稳定性。它限制入口队列和管道缓冲，使用设备 lane 保证同一设备顺序处理，同时避免无限 groupBy 造成饥饿。失败不会悄悄吞掉，而是记录指标和日志，保证运维可观察。

### 12.5 老师问：你怎么证明参数下发真的被设备处理了？

论文依据：第 3.5、5.6 节都强调 publish success 不等于 apply success。

源码回答：

- 后端构造 `params/set`：[`mqtt_publisher.py#L29-L55`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/mqtt_publisher.py#L29-L55)
- 设备解析、校验、应用、ACK：[`param_update_handler.cpp#L22-L72`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/simulator/wokwi/src/comms/mqtt/param_update_handler.cpp#L22-L72)
- Data Hub 存 ACK：[`TdengineRestWriter.java#L249-L286`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/data-hub/src/main/java/com/edgehub/datahub/storage/TdengineRestWriter.java#L249-L286)
- HMI 后端等待并匹配 ACK：[`devices.py#L168-L277`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L168-L277)

可讲答案：

> 我把“命令意图”和“设备确认”分开存储。HMI 后端发布 MQTT 之后，会查询 TDengine 里的 `params_ack`，并比较时间、参数值和 control mode。这样可以区分发布成功、设备拒绝、设备未响应、设备已应用这几种情况。

### 12.6 老师问：AI 是不是自动控制？有没有风险？

论文依据：第 3.7 和第 6.1 明确 decision-support 是辅助机制，不替代操作员和边缘控制器。

源码回答：

- 推荐生成是可解释规则链：[`recommendation_service.py#L35-L76`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/recommendation_service.py#L35-L76)
- 非正常问题都要求确认：[`tuning_engine.py#L80-L91`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/tuning_engine.py#L80-L91)
- 应用 AI 推荐仍走 HMI 后端、MQTT 下发和 ACK：[`devices.py#L1984-L2191`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/api/routes/devices.py#L1984-L2191)

可讲答案：

> AI 在本项目里是 decision support，不是 autonomous controller。它根据历史窗口提取特征、分类问题、生成保守参数建议，但不会直接控制 actuator。是否应用由 operator/admin 在 HMI 确认，应用路径与手动参数更新完全相同。

### 12.7 老师问：第 6 章的应用后验证怎么落到代码？

源码回答：

- 预览仿真计算 baseline 和 recommended 曲线：[`preview_simulator.py#L152-L208`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/preview_simulator.py#L152-L208)
- 实际 telemetry 指标计算：[`post_effect_evaluator.py#L27-L60`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/post_effect_evaluator.py#L27-L60)
- 方向感知比较：[`post_effect_evaluator.py#L82-L94`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/ai/post_effect_evaluator.py#L82-L94)
- 学习闭环评估任务：[`control_action_learning.py#L522-L831`](https://github.com/wanggenAi/edge-hub-temperature-control/blob/3c9f47b3c6e37cbd37f203363b4e3cf06b5c7b6e/hmi/backend/app/services/control_action_learning.py#L522-L831)

可讲答案：

> ACK 只能证明设备处理了命令，不能证明控制效果变好了。所以第 6 章验证的是 baseline、preview 和 actual telemetry 的比较。代码里会计算 in-band ratio、overshoot、settling time、mean absolute error、saturation ratio、temperature swing，并且比较方向是控制意义上的：in-band 越高越好，其他误差/超调/饱和指标越低越好。

### 12.8 老师问：论文里的验证结果能不能说成真实硬件性能？

正确回答：

> 不能直接这样说。论文第 6 章已经限定验证边界：当前结果验证的是软件平台、Wokwi/simulator profile、Data Hub 存储、HMI 展示和应用后验证流程。硬件部分已经有设计资料和迁移方向，但 PCB、MOSFET、传感器位置、加热负载还需要仪器实测。这个边界不是缺点，而是工程诚实：我证明了闭环平台和验证方法，后续真实硬件可以沿用同一套 telemetry、ACK 和指标比较流程。

## 13. 答辩速记版

最值得强调的创新/工程点：

1. 端到端闭环：不是只有控制算法，也包含 MQTT 通信、数据持久化、HMI 操作和 AI 反馈。
2. 边缘端安全：传感器异常和软件过温会锁存故障并强制关闭输出。
3. MQTT 可追溯：`params/set` 和 `params/ack` 分离，能区分“已下发”和“已应用”。
4. Data Hub 可靠性：Reactor 背压、固定 lane 分区、解析容错、TDengine 批量写入。
5. 数据降噪：稳定 telemetry 可跳过原始写入，同时保留摘要，减少时序库压力。
6. 告警状态机：告警有 hold 和 clear 过程，避免瞬时噪声造成抖动。
7. AI 可解释：推荐来自特征、规则分类和有界参数步长，而不是不可控黑盒。
8. Human-in-the-loop：AI 推荐需要人工确认，应用仍走 MQTT 和设备 ACK。
9. 应用后验证：推荐不是点一下就结束，而是比较应用前、预览和实际 telemetry。
10. 学习闭环：控制动作和效果会沉淀为反馈样本，支持后续模型迭代。

一句答辩总结：

> 我的系统实现了从边缘控制、MQTT 通信、数据中枢、时序存储、HMI 操作到 AI 参数优化的完整闭环。核心不是单点算法，而是把控制意图、设备反馈、历史数据和推荐效果都做成可追溯的数据链路，因此既能运行演示，也能支撑后续分析和模型迭代。
