# Development Roadmap

## Stage 1: Repository and Engineering Skeleton Initialization

Goals:

- establish a unified directory structure
- define module boundaries
- create foundational documentation

Deliverables:

- initial README
- directory responsibility notes
- architecture overview document

## Stage 2: Edge Control Node V1 Organization

Goals:

- organize the existing ESP32 and DS18B20 code
- unify parameter naming and log output
- stabilize the minimum runnable closed-loop version

Deliverables:

- first firmware directory layout
- pin and parameter documentation
- log field definitions

## Stage 3: Edge Control Node V2 and Virtual Thermal Model

Goals:

- build a thermal inertia model in Wokwi
- form a closed loop where PWM output affects thermal feedback
- implement a node version that is better suited for demonstration and experiment recording

Deliverables:

- organized simulation project
- thermal model design note
- V2 control flow description

## Stage 4: Experiment Recording and Performance Analysis

Goals:

- record response behavior under different targets and control parameters
- analyze steady-state error and regulation process
- produce raw data for thesis figures and tables

Deliverables:

- experiment logs
- data tables
- plotted curves and summarized observations

## Stage 5: Data Hub and Application Layer Extension

Goals:

- add data upload and routing capability
- introduce storage or a messaging channel
- complete a visualization and parameter configuration interface

Deliverables:

- data path description
- upper-layer application prototype
- three-layer integration note
