# Three-Layer Architecture Overview

## 1. Architectural Goal

This project targets a constant-temperature control scenario and adopts a three-layer architecture to decouple control execution, data routing, and upper-layer applications. The purpose is to improve scalability, maintainability, and clarity for thesis presentation.

The system is divided into:

1. Edge Control Layer
2. Data Hub Layer
3. Application Decision Layer

## 2. Edge Control Layer

The edge control layer interacts directly with the controlled object and actuation hardware, with an emphasis on real-time behavior and closed-loop capability.

Main responsibilities:

- acquire temperature data
- execute local control logic
- generate PWM output
- report node status and debugging information
- provide standardized data interfaces for upper layers

Current implementation baseline:

- controller: ESP32
- sensor: DS18B20
- output method: PWM
- control strategy path: threshold control, proportional control, then simplified PID

## 3. Data Hub Layer

The data hub layer sits between the edge node and upper-layer applications. Its main role is to receive, normalize, route, and store system data.

Main responsibilities:

- receive data uploaded by edge nodes
- unify data formats
- support message routing and state synchronization
- support experiment logging and later analysis

This layer is not the implementation focus at the current stage, but expansion space is reserved in both repository structure and interface design.

## 4. Application Decision Layer

The application decision layer is user-facing and focuses on system operation and management.

Main responsibilities:

- temperature and status visualization
- target temperature configuration
- control parameter management
- experiment and runtime result presentation
- later optimization or intelligent decision extensions

This layer is not the current development priority, but its expected interface needs still influence the output format design of the lower layers.

## 5. Current Implementation Priority

The current phase focuses on:

1. making the temperature acquisition loop run reliably
2. making PWM control output stable
3. building a simulation closed loop based on a virtual thermal model
4. ensuring experiments are recordable, explainable, and repeatable

These items directly support the "System Implementation" and "Experimental Validation" sections of the thesis.
