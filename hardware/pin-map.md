# ESP32 Pin Map

This document records the current pin assignment of the edge temperature-control node. Its purpose is to keep the simulation implementation and future hardware design aligned.

## Current Pin Allocation

| Signal / Module | ESP32 Pin | Direction | Current Role | Notes |
| --- | --- | --- | --- | --- |
| DS18B20 data line | GPIO21 | Input / bidirectional | Temperature sensor interface | Uses a 4.7 k pull-up resistor to 3.3 V in the current simulation |
| Status LED | GPIO2 | Output | Heartbeat and runtime status indication | Used to indicate that the controller loop is active |
| PWM output | GPIO18 | Output | Control output for the heating drive path | Currently observed in simulation and intended for later MOSFET driving |
| Serial TX | TX | Output | Runtime log output | Connected to the Wokwi Serial Monitor in simulation |
| Serial RX | RX | Input | Serial monitor return path | Reserved mainly for simulation and debugging |

## Power and Ground Notes

| Connection | Current Use | Notes |
| --- | --- | --- |
| 3.3 V | ESP32 and DS18B20 supply reference in simulation | The real hardware stage will require a proper regulated 3.3 V rail |
| GND | Common reference ground | Sensor, controller, and output stage must share a consistent ground reference |

## Current Interpretation

- GPIO21 is the main temperature sensing interface.
- GPIO2 is reserved for simple status indication.
- GPIO18 is the main actuation-output signal in the current design path.

These assignments are already consistent with the current Wokwi implementation and should be preserved unless there is a clear hardware-design reason to change them later.

## Reserved Expansion Direction

At later stages, the hardware design may need additional pins for:

- communication interfaces
- parameter configuration or local user input
- more advanced status indication
- optional protection or monitoring signals

Those pins are not formally assigned yet in the current stage.
