# esp32-temperature-node

This directory is reserved for the ESP32 temperature control node firmware.

Suggested version progression:

- V1: minimum validation with sensing, PWM, and serial output
- V2: improved module structure, unified parameter configuration, and standardized logs
- V3: communication interfaces and more stable control strategies

Recommended future code layout:

- `src/main.*`: main loop and scheduling
- `src/sensors/*`: temperature acquisition
- `src/control/*`: control algorithms
- `src/drivers/*`: PWM and status indication
- `src/common/*`: constants, configuration, and log structures
