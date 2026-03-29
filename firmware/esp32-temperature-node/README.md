# esp32-temperature-node

该目录预留给 ESP32 温控节点固件实现。

建议后续版本演进方式：

- V1：最小运行验证，完成采温、PWM、串口输出
- V2：整理模块结构，统一参数配置与日志输出
- V3：增加通信接口与更稳定的控制策略

推荐后续代码拆分方向：

- `src/main.*`：主循环与调度
- `src/sensors/*`：温度采集
- `src/control/*`：控制算法
- `src/drivers/*`：PWM 与状态指示
- `src/common/*`：常量、配置、日志结构
