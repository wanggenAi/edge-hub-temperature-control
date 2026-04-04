# Real Hardware Implementations

This directory contains real hardware drivers that implement the existing
interfaces.

- `RealDs18b20Sensor`: DS18B20 OneWire temperature sensor on `GPIO21`
- `MosfetHeater`: low-side MOSFET heater driver on `GPIO18` PWM

Notes:
- The status LED remains controlled by `EdgeTemperatureApp` on `GPIO2`.
- Wokwi and real-hardware assembly are switched by build macro.
- Application logic is shared across both modes:
  `MQTT / params / ack / runtime config`.
