# 答辩演示 Runbook

目标：让答辩演示能稳定证明项目最有价值的闭环能力，而不是只展示静态页面。

核心演示链路：

```text
HMI 页面修改目标温度
-> HMI 后端发布 MQTT params/set
-> Wokwi/硬件 edge-node-001 接收并应用参数
-> 设备发布 params/ack 和 telemetry
-> Java DataHub 消费 MQTT 并写入 TDengine
-> HMI 从 TDengine 看到目标值、实时温度和在线状态变化
```

## 1. 演示设备

### 主演示设备

- 设备编号：`edge-node-001`
- 代码位置：`simulator/wokwi/src/config/app_config.h`
- MQTT telemetry：`edge/temperature/edge-node-001/telemetry`
- MQTT 参数下发：`edge/temperature/edge-node-001/params/set`
- MQTT ACK：`edge/temperature/edge-node-001/params/ack`
- 用途：正式演示 HMI -> MQTT -> 设备 ACK -> DataHub -> TDengine -> HMI 的真实闭环。

答辩时优先使用 Wokwi/真实硬件运行这个设备。Python live edge 只作为明天自测和现场兜底，不作为主叙事。

### 造数设备

运行 `seed_defense_demo.py` 后会生成 6 个 `DEF-*` 设备，用来展示 AI 诊断、历史对比、告警和应用后验证：

| 设备 | 主题 | 演示价值 |
|---|---|---|
| `DEF-STABLE-01` | 稳定闭环 | 证明系统不是只会报错，也能识别正常状态 |
| `DEF-SLOW-01` | 慢响应 | 展示特征诊断和安全增益建议 |
| `DEF-OSC-01` | 振荡 | 展示振荡证据、阻尼建议、预览和反馈样本 |
| `DEF-OVS-01` | 超调 | 展示保守调参和过冲降低 |
| `DEF-SAT-01` | 执行器饱和 | 展示系统知道 PID 不能解决硬件能力边界 |
| `DEF-SSE-01` | 稳态误差 | 展示积分修正和应用后验证 |

## 2. 明天自测顺序

所有命令默认从仓库根目录执行：

```bash
cd /Users/seker./edge-hub-temperature-control
```

### 2.1 启动 HMI、AI 和中间件

这个命令会启动 PostgreSQL、TDengine、AI runtime、HMI 后端和 HMI 前端：

```bash
./scripts/start-hmi-dev.sh --with-docker --skip-install --restart
```

预期地址：

- HMI 前端：`http://127.0.0.1:5173`
- HMI 后端：`http://127.0.0.1:8000/docs`
- AI runtime：`http://127.0.0.1:8010/health`
- TDengine REST：`http://127.0.0.1:6041`

登录账号：

- 用户名：`admin`
- 密码：`admin123`

### 2.2 生成答辩造数数据

先确保基础用户、规则和预览案例存在：

```bash
hmi/backend/.venv/bin/python hmi/backend/scripts/db_seed.py --rules --demo --preview-ai-demo
```

确保正式闭环演示设备 `edge-node-001` 已经在 HMI 数据库里，页面能搜索到它：

```bash
hmi/backend/.venv/bin/python hmi/backend/scripts/ensure_defense_live_device.py
```

再生成高信号答辩数据：

```bash
hmi/backend/.venv/bin/python hmi/backend/scripts/seed_defense_demo.py --reset --minutes 180 --step-seconds 15
```

这一步只重置 `DEF-*` 设备，不会删除 `edge-node-001`。

### 2.3 启动 DataHub

DataHub 需要单独启动，保持这个终端不要关：

```bash
cd /Users/seker./edge-hub-temperature-control/data-hub
./gradlew bootRun
```

预期配置：

- DataHub 主端口：`18080`
- Actuator/Prometheus：`8081`
- MQTT broker：读取 `data-hub/config/application.properties`
- TDengine 写入模式：`tdengine-rest`

健康检查：

```bash
curl http://127.0.0.1:8081/actuator/health
```

### 2.4 编译并启动 Wokwi

编译固件：

```bash
cd /Users/seker./edge-hub-temperature-control/simulator/wokwi
pio run -e esp32dev
```

然后在 VS Code 里打开 `simulator/wokwi`，用 Wokwi 扩展启动仿真。

串口日志重点看这些字段：

```text
edge_temperature_app_boot=ok
runtime_config_load_status=loaded_from_nvs
runtime_target_temp_c=...
mqtt_telemetry_topic=edge/temperature/edge-node-001/telemetry
mqtt_params_topic=edge/temperature/edge-node-001/params/set
mqtt_params_ack_topic=edge/temperature/edge-node-001/params/ack
```

如果第一次运行没有 NVS，应该看到默认目标温度来自代码配置，当前默认是 `23.0°C`，不是旧的 `35.0°C`。

检查 Wokwi 串口桥是否开启：

```bash
nc -vz 127.0.0.1 4000
```

### 2.5 运行预检查

回到仓库根目录：

```bash
cd /Users/seker./edge-hub-temperature-control
hmi/backend/.venv/bin/python scripts/preflight-defense-demo.py --require-wokwi
```

如果还没启动 Wokwi，可以先不加 `--require-wokwi`：

```bash
hmi/backend/.venv/bin/python scripts/preflight-defense-demo.py
```

预检查会看：

- PostgreSQL / TDengine Docker 是否运行
- HMI 后端、前端、AI runtime 是否健康
- DataHub actuator 是否健康
- DataHub 是否没有占用 `8080`
- Wokwi 串口端口 `4000`
- `edge-node-001` 是否存在于 PostgreSQL
- `DEF-*` 造数设备是否存在
- TDengine 中 `device_status`、`telemetry`、`params_ack` 的最新状态

### 2.6 自动验证真实闭环

Wokwi 已经在线后，先把目标改成 25：

```bash
hmi/backend/.venv/bin/python hmi/backend/scripts/verify_target_update_flow.py --target-temp 25 --timeout 20
```

再改回 23，保证正式演示前回到温和初始状态：

```bash
hmi/backend/.venv/bin/python hmi/backend/scripts/verify_target_update_flow.py --target-temp 23 --timeout 20
```

看到下面这行才算闭环自测通过：

```text
[pass] target update closed-loop verified
```

这个验证脚本实际检查的是：

- HMI 登录成功
- HMI 找到 `edge-node-001`
- DataHub `device_status` 显示在线
- HMI API 发布参数
- TDengine 出现 `params_set`
- 设备返回匹配目标值的 `params_ack`
- TDengine 出现目标值匹配的 `telemetry`
- HMI 详情页接口反映新目标值

## 3. 正式答辩演示流程

### 3.1 开场说法

可以这样讲：

> 我这个系统不是单纯的温度看板，而是端到端闭环温控平台。页面上的目标温度修改，会通过 HMI 后端发布到 MQTT；边缘设备收到后要进行参数校验、应用并返回 ACK；DataHub 消费 telemetry、params/set 和 params/ack 写入 TDengine；最后 HMI 从时序库看到实时状态变化。这里重点不是某个页面，而是控制意图、设备确认和时序证据形成闭环。

### 3.2 现场操作

1. 打开 `http://127.0.0.1:5173`，登录 `admin / admin123`。
2. 进入 `edge-node-001` 设备详情页。
3. 指出页面当前状态：
   - `Comm = Online`
   - 当前温度、目标温度、PWM 输出
   - 曲线正在刷新
4. 修改目标温度，例如从 `23` 改到 `25`。
5. 保存参数。
6. 切到 DataHub 终端，指出收到了 `params/set`、`params/ack`、`telemetry`。
7. 回到页面，观察目标值和温度曲线变化。
8. 说明这一步证明的链路：
   `页面 -> HMI API -> MQTT -> 设备 -> ACK -> DataHub -> TDengine -> 页面`。

### 3.3 用 TDengine 证明不是假数据

现场可以运行：

```bash
docker exec edgehub-tdengine taos -s "use edgehub; select ts,target_temp_c,kp,ki,kd,control_mode from params_set where device_id='edge-node-001' order by ts desc limit 5; select ts,ack_type,success,reason,target_temp_c,kp,ki,kd,control_mode from params_ack where device_id='edge-node-001' order by ts desc limit 5; select ts,target_temp_c,sensor_temp_c,sim_temp_c,pwm_duty,run_id from telemetry where device_id='edge-node-001' order by ts desc limit 5;"
```

解释口径：

> `params_set` 是上位机控制意图，`params_ack` 是设备确认结果，`telemetry` 是设备运行事实。三张表同时出现同一个目标温度，说明不是前端本地改了一个数字。

### 3.4 展示 AI 和论文价值

闭环演示完成后，再切换到 `DEF-*` 设备讲系统价值：

1. `DEF-OSC-01`：展示振荡识别、推荐降 Kp/增加阻尼、预览曲线和应用后反馈。
2. `DEF-OVS-01`：展示超调问题和保守参数建议。
3. `DEF-SAT-01`：强调执行器饱和不是靠盲目加 PID 解决，系统能识别硬件边界。
4. `DEF-SSE-01`：展示稳态误差和积分修正。
5. 打开 `/history`：展示历史窗口、摘要和对比。
6. 打开 `/alarms`：展示告警来自 DataHub 规则和设备状态，不是前端写死。
7. 打开 `/ops`：展示 DataHub 指标、AI runtime 状态和工程运行可观测性。

建议叙事：

> 第一部分证明真实闭环能跑通，第二部分证明系统能把运行数据转化为诊断、推荐、预览和应用后验证。这就是论文里“边缘闭环 + 数据中枢 + HMI + AI 决策支持”的完整价值。

## 4. 兜底方案

如果 Wokwi 临场跑不起来，但 HMI、DataHub、TDengine 都正常，可以用 Python live edge 作为兜底设备。这个兜底仍然走真实 MQTT 和 DataHub，不直接写 TDengine。

```bash
cd /Users/seker./edge-hub-temperature-control/hmi/backend
.venv/bin/python scripts/live_thermal_edge_node.py \
  --device-id edge-node-001 \
  --environment defense_live \
  --target-temp 23 \
  --start-temp 23 \
  --kp 120 --ki 12 --kd 0 \
  --seconds 0 \
  --log-every 5
```

兜底时要诚实说明：

> 这里用的是软件边缘节点替代 Wokwi 硬件仿真，但 MQTT、DataHub、TDengine 和 HMI 都仍然是真实链路。正式硬件/Wokwi 代码使用同一套 topic 和 payload contract。

## 5. 常用排查命令

看 HMI 状态：

```bash
./scripts/start-hmi-dev.sh --status
```

看 HMI 日志：

```bash
tail -f runtime/logs/dev/hmi-backend.log
tail -f runtime/logs/dev/hmi-frontend.log
tail -f runtime/logs/dev/ai-runtime.log
```

看 DataHub 健康：

```bash
curl http://127.0.0.1:8081/actuator/health
```

看 DataHub 最新设备状态：

```bash
docker exec edgehub-tdengine taos -s "use edgehub; select ts,last_seen_ts,online,status_reason,last_message_kind from device_status where device_id='edge-node-001' order by ts desc limit 5;"
```

看端口：

```bash
lsof -nP -iTCP:5173 -sTCP:LISTEN
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:8010 -sTCP:LISTEN
lsof -nP -iTCP:8081 -sTCP:LISTEN
lsof -nP -iTCP:18080 -sTCP:LISTEN
lsof -nP -iTCP:8080 -sTCP:LISTEN
```

停止 HMI：

```bash
./scripts/stop-hmi-dev.sh
```

停止 HMI 和 Docker 中间件：

```bash
./scripts/stop-hmi-dev.sh --with-docker-down
```

## 6. 注意事项

- DataHub 不由 `start-hmi-dev.sh` 启动，需要单独 `./gradlew bootRun`。
- HMI 一键脚本会启动 PostgreSQL 和 TDengine，但不会启动 Wokwi。
- 当前 Java DataHub 源码没有 Redis 依赖，Redis 不是答辩主链路必需项。
- DataHub 主端口已经改为 `18080`，避免影响你自己的 `8080` 服务。
- `MQTT_PUBLISH_RETAIN=false`，正式演示不依赖 retained 参数。
- 设备重启后的目标温度由 NVS 优先恢复；如果没有 NVS，则使用代码默认 `23.0°C`。
- 演示前用 `verify_target_update_flow.py --target-temp 23` 把现场设备恢复到温和初始目标。
