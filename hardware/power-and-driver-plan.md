# Power and Driver Plan

## 1. Purpose

This document records the current design-level plan for the power path and actuator-driving path of the edge temperature-control node.

It is a staged engineering note, not a completed board-level circuit design.

## 2. Why a Separate Power Plan Is Needed

The simulation environment can validate control logic and signal interaction, but a real hardware system must also handle electrical power delivery correctly.

In a practical temperature-control node:

- the ESP32 requires a stable low-voltage supply
- the DS18B20 requires a compatible logic and supply level
- the heating load may require more current and a different power path than the controller itself

For that reason, the real system cannot rely only on the logical signal connections shown in simulation.

## 3. Likely Input-Power Form

At the current planning stage, a realistic system would likely use an external DC power source.

Typical reasons:

- the controller and the load may have different power demands
- a separate DC source is easier to reason about in an embedded temperature-control scenario
- it provides a clearer path toward later experiments with heating loads

The exact voltage level is not fixed yet at this stage.

## 4. Why Voltage Regulation Is Needed

Even if the future system uses an external DC supply, the ESP32 and DS18B20 still require a suitable low-voltage rail.

This implies the need for a regulation stage, for example:

- external DC input
- step-down or regulated supply stage
- stable 3.3 V rail for ESP32 and sensor logic

The purpose of this stage is:

- provide a stable controller supply
- avoid exposing the ESP32 and sensor directly to an unsuitable input voltage
- improve the realism of the future hardware design

## 5. Low-Side MOSFET Driving Concept

The current actuator-driving direction is a low-side MOSFET switching structure.

Basic concept:

1. the load is connected to the positive supply side
2. the MOSFET is placed on the low side between the load and ground
3. the ESP32 PWM signal drives the MOSFET gate
4. the MOSFET switches the load current path according to the PWM duty cycle

This approach is appropriate for the current project because:

- it is relatively simple to explain
- it is commonly used in embedded control applications
- it matches the PWM-based control structure already validated in simulation

## 6. Gate and Resistor Notes

The following concepts should be included in the later real hardware design:

- gate resistor:
  - helps limit switching-edge stress and improves gate-drive behavior
- gate pull-down resistor:
  - helps ensure the MOSFET remains off when the control signal is floating or during startup
- load connection:
  - the heating element or equivalent load must be connected in a clearly defined current path
- power return path:
  - the load current and controller ground must be designed with a consistent reference strategy

These are not yet implemented as a final circuit in the repository, but they are already part of the intended hardware direction.

## 7. Why the Project Does Not Jump Directly to a Full Power Circuit

At the current stage, the project first prioritizes:

- control logic correctness
- closed-loop behavior verification
- experiment repeatability
- architecture clarity

This is intentional.

If the project tried to complete the full power circuit, controller logic, and board-level implementation all at once, it would increase complexity too early and make it harder to isolate problems. The current step-by-step approach is more suitable for an undergraduate engineering project and more consistent with clear thesis presentation.

## 8. Current Stage Conclusion

The present power and driver design should be understood as a planned hardware path rather than a finalized hardware circuit.

The simulation has already validated the control-output logic. The next hardware stage is to translate that logic into a proper electrical design with:

- defined input power
- regulated controller supply
- MOSFET drive path
- load interface
- grounding and protection details
