# Schematic Notes

## 1. Purpose

This document clarifies the difference between the current simulation connection description and a future formal hardware schematic.

Its purpose is to prevent the project from overstating the current hardware progress while still preserving the value of the simulation work.

## 2. What the Current Wokwi Diagram Can Express

The current Wokwi `diagram.json` can express:

- which main components are connected in the simulation
- which GPIO pins are used
- the logical direction of the sensing and output paths
- basic pull-up and LED resistor usage
- serial-monitor connection for debugging

This is useful for:

- firmware bring-up
- signal-path verification
- pin mapping validation
- simulation-based demonstration

## 3. What the Wokwi Diagram Cannot Replace

The current Wokwi connection should not be treated as a replacement for:

- a formal electrical schematic
- a complete power-tree design
- connector and interface definition
- board-level grounding strategy
- protection-circuit design
- manufacturable PCB documentation

In other words, the Wokwi connection diagram is a simulation aid, not a final engineering drawing.

## 4. What a Formal Hardware Schematic Still Needs

If the project proceeds toward a formal schematic, at minimum the following blocks still need to be defined clearly:

### 4.1 Power Input

- external input connector
- input-voltage definition
- polarity and current-path definition

### 4.2 Voltage Regulation

- regulated supply path for ESP32
- regulated logic supply path for the sensor
- decoupling and supply stability considerations

### 4.3 ESP32 Main Control Block

- power pins
- boot and enable requirements if needed
- programming/debug interface considerations

### 4.4 DS18B20 Interface Block

- data-line connection
- pull-up resistor placement
- supply and ground definition

### 4.5 MOSFET Driver and Heating Load Block

- PWM control signal path
- MOSFET gate resistor
- gate pull-down resistor
- load connection
- load power return path

### 4.6 Grounding and Supply Relationship

- controller ground reference
- sensor ground reference
- load current return path
- relationship between low-power and load-side current loops

### 4.7 Optional Protection and Reliability Elements

Depending on the later hardware scope, optional additions may include:

- input protection
- reverse-polarity protection
- fuse or current-limiting design
- transient suppression

## 5. Why the Final Schematic Is Not Completed Yet

At the current stage, the project is still in a simulation-led development phase.

This is reasonable because:

- the control logic needed to be verified first
- the closed-loop behavior needed to be observed before committing to a more detailed hardware path
- the staged approach makes the thesis easier to structure and explain
- the hardware design can now be built on validated control behavior rather than on assumptions alone

## 6. Current Position

The correct engineering interpretation of the current repository is:

- the simulation connection diagram already validates the basic logic of sensing, PWM output, and runtime observation
- the formal schematic has not yet been completed
- the hardware design documentation is now being prepared so the next stage can move toward a proper real-world electrical design in a controlled way
