# simulator

This directory stores simulation-related assets, currently centered on Wokwi.

Current active simulation path:

- `simulator/wokwi`

The simulation objective is not just to show a sensor reading. It is to gradually build an explainable virtual closed-loop temperature control system:

1. the controller outputs PWM
2. the thermal model updates state according to PWM input and environmental cooling
3. the measured temperature is fed back to the controller
4. the controller adjusts output again

Suggested future contents:

- Wokwi project files
- thermal inertia model notes
- control node V1 and V2 descriptions
- simulation screenshots and observation records

The simulation baseline is actively used by both:

- `data-hub` MQTT ingestion tests
- `hmi` realtime and history demos

Documentation sync date: 2026-04-04.
