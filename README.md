# Design and Implementation of a Three-Layer Architecture for Edge Control, Data Hub, and Application Decision in Constant Temperature Scenarios

This repository hosts the full engineering implementation, design documents, simulation assets, experiment records, and thesis-supporting materials for an undergraduate computer engineering graduation project.

The core objective of this project is not to build an AI-centric system. Instead, it is to engineer a practical three-layer architecture for a temperature control scenario:

1. Edge Control Layer: temperature sensing, PWM control, device actuation, and local closed-loop behavior.
2. Data Hub Layer: data ingestion, storage, message routing, and system decoupling.
3. Application Decision Layer: visualization, parameter configuration, monitoring, and future optimization extensions.

At the current stage, the main focus is the edge control layer and the simulation environment, with priority given to a closed-loop temperature control node that is demonstrable, verifiable, and extensible.

## Current Runnable Module

The repository now includes a first runnable engineering result:

- `simulator/wokwi`

The repository also includes an initial deployment-document area:

- `docs/deployment`

This module contains the validated Wokwi-based edge node simulation for ESP32, DS18B20 sensing, heartbeat LED indication, GPIO18 PWM output, and simple proportional control V1.

## Quick Start

If you want to start from the current runnable result, read:

- `simulator/wokwi/README.md`
- `docs/deployment/mqtt-broker-ubuntu.md`

That directory contains the Wokwi project files and the instructions for running the current edge-layer simulation.

## 1. Project Background

Many traditional temperature control implementations focus only on local control logic and do not provide an integrated engineering design from the control node to data flow and upper-layer applications. To better align with realistic embedded and industrial scenarios, this project adopts a three-layer architecture so that control execution, data routing, and user-facing applications are clearly decoupled. This also improves extensibility, maintainability, and thesis readability.

The project uses ESP32 as the edge controller, DS18B20 as the primary temperature sensor, and PWM as the control output. Development starts with Wokwi-based simulation and then evolves toward a deployable real-hardware solution.

## 2. Confirmed Technical Baseline

### 2.1 Hardware and Control Foundation

- Main controller: ESP32
- Primary temperature sensor: DS18B20
- Actuation output: PWM
- Power driving approach: low-side MOSFET driving
- Control cycle: approximately 1 second
- Target temperature range: 25 C to 45 C

### 2.2 Current Progress

- ESP32 minimum runtime validation
- Serial output
- DS18B20 temperature reading
- LED status indication
- PWM output testing
- Simple proportional control V1 based on target temperature

### 2.3 Current Control Targets

- Temperature measurement accuracy target: around +/-0.5 C
- Steady-state control error target: <= +/-1.0 C
- Output form: PWM
- Current algorithm evolution priority: threshold control -> proportional control -> simplified PID

## 3. Repository Structure

```text
edge-hub-temperature-control/
├── docs/                  Project documents, design notes, interface specs, experiment templates
├── hardware/              Hardware notes, pin definitions, real-hardware implementation plan
├── simulator/             Wokwi simulation, thermal model, virtual closed-loop behavior
├── experiments/           Experiment records, observed data, and analysis
├── scripts/               Data-processing and helper scripts
└── README.md              Project overview
```

## 4. Directory Responsibilities

### `docs/`

Stores descriptive project documentation, including:

- overall system architecture
- module responsibility definitions
- interface design
- development plan
- experiment record templates

### `hardware/`

Stores real-hardware-related content, including:

- ESP32 pin mapping
- DS18B20 wiring plan
- PWM and low-side MOSFET driving notes
- later schematics, wiring diagrams, and component selection notes

### `simulator/`

Stores simulation-related assets, including:

- Wokwi projects
- virtual thermal inertia models
- closed-loop temperature control demonstrations
- simulation configuration and documentation

### `experiments/`

Stores experiment materials, including:

- control parameter records
- step-response experiments
- steady-state error experiments
- simulation result notes and screenshots

### `scripts/`

Stores helper utilities such as:

- experiment data processing scripts
- serial log parsing scripts
- CSV conversion and plotting scripts

## 5. Current Development Roadmap

### Stage 1: Minimum Closed-Loop Validation for the Edge Node

- complete temperature acquisition
- complete PWM output
- complete threshold/proportional control
- complete serial observation

### Stage 2: Virtual Thermal Model Closed-Loop Simulation

- build a thermal inertia model in Wokwi where temperature changes with PWM output
- form a demonstration loop where control output affects thermal feedback
- record control cycle, response time, and steady-state error

### Stage 3: Edge Node Engineering Refinement

- split modules clearly
- centralize parameter configuration
- standardize log output format
- reserve interfaces for later communication access

### Stage 4: Data Hub and Application Layer Extension

- data ingestion and storage
- message flow
- visualization interface
- parameter configuration and runtime monitoring
- later optimization algorithm extensions

## 6. Recommended Near-Term Tasks

1. Organize the current Wokwi simulation project.
2. Implement temperature control node V2.
3. Introduce a virtual thermal model so temperature changes dynamically with PWM duty cycle.
4. Standardize the serial log format to support experiments and thesis references.
5. Create the first version of the experiment record template.

## 7. Development Conventions

The repository is currently in its initialization phase. The following conventions are recommended:

- define module boundaries before adding complexity
- advance one clear objective per iteration
- keep experimental parameters, observations, and results for every test
- prioritize readability, maintainability, and explainability in all code

When simulation modules are populated with runnable content, local documentation should describe the exact execution workflow.

## 8. Next Step

The next priority is:

1. organize the low-level simulation code structure
2. implement temperature control node V2 with a virtual thermal model for a demonstrable closed-loop simulation

This will become the engineering foundation for the "System Implementation" and "Experimental Validation" chapters of the thesis.
