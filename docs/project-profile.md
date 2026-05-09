# Project Profile

## 1. What This Project Is

This repository is an end-to-end intelligent temperature-control engineering
system built around four active runtime/data layers:

1. edge control (`simulator/wokwi`)
2. message + ingestion (`MQTT broker` + `data-hub`)
3. application + operations (`hmi`)
4. offline learning + feedback pipeline (`ml` + `hmi/backend/ai`)

In its current form, the project is no longer just a temperature visualization
demo or a standalone control algorithm exercise.

It is better described as:

- a real-time edge temperature-control platform
- with MQTT-based device communication
- with time-series persistence and operations visibility
- with AI-assisted PID tuning recommendation
- and with post-apply effect validation

This framing matches the actual codebase more accurately than a narrow
"temperature dashboard" description.

## 2. High-Level Runtime Story

The main runtime loop implemented by the repository is:

```text
edge node telemetry
-> MQTT broker
-> Java data-hub ingest / parse / route / persist
-> TDengine + PostgreSQL-backed HMI views
-> AI-assisted recommendation / preview / apply
-> MQTT params/set back to device
-> params/ack and post-apply telemetry validation
```

This means the repository already supports a closed engineering loop rather than
just one-way monitoring.

## 3. Layer-By-Layer Reading

### 3.1 Edge Control Layer

Main location:

- `simulator/wokwi`

Current role:

- runs an ESP32-oriented temperature-control node
- supports Wokwi simulation and real-hardware build profiles
- executes local PI/PID-compatible control logic
- publishes telemetry through MQTT
- subscribes to `params/set`
- publishes `params/ack`

Important implementation signals:

- [sketch.ino](../simulator/wokwi/src/sketch.ino)
- [edge_app.cpp](../simulator/wokwi/src/app/edge_app.cpp)
- [pi_controller.cpp](../simulator/wokwi/src/controller/pi_controller.cpp)
- [mqtt_gateway.cpp](../simulator/wokwi/src/comms/mqtt/mqtt_gateway.cpp)

What is actually implemented:

- local control tick execution
- runtime parameter store
- bounded-integral PI controller with derivative-compatible interface
- software safety latch
- MQTT telemetry publish
- MQTT parameter downlink handling
- ACK publish path
- simulator thermal model

Current engineering meaning:

- the edge side is not just a payload mocker
- it is a real closed-loop control node abstraction
- it already supports thesis-worthy experiments such as overshoot, settling,
  parameter tuning, and runtime reconfiguration

### 3.2 Messaging And Ingestion Layer

Main locations:

- external MQTT broker (Mosquitto or compatible)
- `data-hub`

Current role:

- receives telemetry / `params/set` / `params/ack`
- parses and normalizes messages
- applies bounded backpressure
- persists into TDengine or logs
- tracks device status and summary windows
- exposes operational observability

Important implementation signals:

- [ReactiveMqttConsumer.java](../data-hub/src/main/java/com/edgehub/datahub/mqtt/ReactiveMqttConsumer.java)
- [MqttConsumePipeline.java](../data-hub/src/main/java/com/edgehub/datahub/pipeline/MqttConsumePipeline.java)
- [HubProperties.java](../data-hub/src/main/java/com/edgehub/datahub/config/HubProperties.java)
- [data-hub/README.md](../data-hub/README.md)

What is actually implemented:

- HiveMQ-based async MQTT consumer
- topic subscription for telemetry, set, ack, and config topics
- bounded ingress queue + bounded pipeline buffer
- overflow strategies and metrics
- telemetry filtering and summary aggregation
- device online/offline tracking
- periodic `datahub.stats` observability logs
- Prometheus/Actuator metrics for JVM/runtime visibility

Current engineering meaning:

- this layer is one of the strongest "system engineering" parts of the repo
- it gives the project real middleware depth beyond UI and control logic
- it is especially useful in a thesis because it demonstrates performance,
  reliability, and scalability thinking

### 3.3 Application And Operations Layer

Main location:

- `hmi`

Current role:

- provides user-facing monitoring and control
- manages users, roles, devices, parameters, and alarm rules
- reads telemetry/history from TDengine
- publishes control intents through MQTT
- provides operator and developer observability views

Important implementation signals:

- [main.py](../hmi/backend/app/main.py)
- [devices.py](../hmi/backend/app/api/routes/devices.py)
- [mqtt_publisher.py](../hmi/backend/app/services/mqtt_publisher.py)
- [device-detail-page.tsx](../hmi/frontend/src/pages/device-detail-page.tsx)
- [ops-page.tsx](../hmi/frontend/src/pages/ops-page.tsx)

What is actually implemented:

- JWT login and RBAC
- multi-device access control
- device overview / detail / history / alarms / storage rules pages
- MQTT parameter publish from backend
- ACK-aware AI recommendation apply path
- developer Ops Console
- AI-specific observability views

Current engineering meaning:

- the HMI is not just a CRUD frontend
- it acts as the control-plane and operations surface of the system
- this is important for thesis positioning because it makes the project look
  like a complete platform instead of a single algorithm demo

### 3.4 AI Decision Support Layer

Main locations:

- `hmi/backend/app/services/ai`
- `hmi/backend/ai/scripts`
- `hmi/frontend/src/pages/ai-page.tsx`

Current role:

- diagnose control problems from telemetry history
- generate PID recommendations
- optionally rank recommendation candidates with trained models
- simulate preview curves before apply
- validate actual post-apply effect after apply
- accumulate feedback samples for offline learning

Important implementation signals:

- [feature_extractor.py](../hmi/backend/app/services/ai/feature_extractor.py)
- [problem_classifier.py](../hmi/backend/app/services/ai/problem_classifier.py)
- [tuning_engine.py](../hmi/backend/app/services/ai/tuning_engine.py)
- [recommendation_service.py](../hmi/backend/app/services/ai/recommendation_service.py)
- [recommendation_orchestrator.py](../hmi/backend/app/services/ai/recommendation_orchestrator.py)
- [recommendation_ranker.py](../hmi/backend/app/services/ai/recommendation_ranker.py)
- [preview_simulator.py](../hmi/backend/app/services/ai/preview_simulator.py)
- [post_effect_evaluator.py](../hmi/backend/app/services/ai/post_effect_evaluator.py)
- [ai-page.tsx](../hmi/frontend/src/pages/ai-page.tsx)

What is actually implemented:

- rule-based feature extraction from telemetry windows
- problem classification for:
  - `normal`
  - `slow_response`
  - `steady_state_error`
  - `overshoot_high`
  - `oscillation`
  - `saturation_limited`
- rule-based parameter tuning engine
- optional model-based ranking around a rule-center candidate
- preview simulation before apply
- actual-effect evaluation after apply
- telemetry comparison among baseline / preview / actual
- independent AI runtime service
- fallback to local backend recommendation flow when runtime service is unavailable

Current engineering meaning:

- the AI layer is not a placeholder
- it is a real, explainable decision-support subsystem
- the strongest thesis claim is not "automatic control by AI"
- the strongest thesis claim is:
  "AI-assisted, explainable PID optimization with pre-apply preview and post-apply validation"

### 3.5 Offline ML And Feedback Pipeline

Main locations:

- `ml`
- `hmi/backend/ai/scripts`
- `hmi/backend/app/services/control_action_learning.py`

Current role:

- export telemetry and action feedback
- prepare offline datasets
- train evaluation/ranking models
- maintain a control-action feedback learning loop

Important implementation signals:

- [ml/README.md](../ml/README.md)
- [control_action_learning.py](../hmi/backend/app/services/control_action_learning.py)
- [run_control_action_feedback_worker.py](../hmi/backend/scripts/run_control_action_feedback_worker.py)
- [model_lifecycle_service.py](../hmi/backend/app/services/ai/model_lifecycle_service.py)

What is actually implemented:

- TDengine export to parquet
- cleaned sliding-window dataset preparation
- pseudo-label generation for problem types
- control-action feedback sample generation
- recommendation success model training
- preview-gap model training
- model lifecycle metadata / observability

Current engineering meaning:

- this layer gives the project a real "learning system" story
- it is not only online inference
- it includes data preparation, labeling, evaluation, and model iteration

## 4. MQTT Contract In Practice

The project is organized around three core MQTT message flows:

- telemetry
- `params/set`
- `params/ack`

Design reference:

- [docs/mqtt_interface.md](mqtt_interface.md)

Actual implementation status:

- telemetry: implemented
- `params/set`: implemented
- `params/ack`: implemented
- optimizer recommendation topic: still mostly conceptual / reserved as a future
  device-side direct channel

This distinction matters for thesis writing: the intelligent recommendation
system exists today, but its decision path mainly lives in HMI/backend/AI logic
rather than as a standalone MQTT optimizer topic consumed directly by the edge.

## 5. What The Project Is Best At

The repository is strongest in these areas:

1. end-to-end closed engineering loop
2. real MQTT + ingest + persistence pipeline
3. developer/operator observability
4. explainable AI-assisted PID recommendation
5. post-apply validation and learning feedback accumulation

These strengths are much more valuable in a defense than claiming novelty in any
single isolated algorithm.

## 6. Current Boundaries

Several boundaries are explicit in the current codebase and should be described
honestly:

- the edge-side plant is still a simplified thermal model in simulation mode
- the current controller is PI/PID-compatible but not a full industrial control
  stack
- AI diagnosis and recommendation are explainable and structured, but they are
  not a fully autonomous closed-loop controller
- some AI ranking behavior depends on local trained artifacts being present
- demo and evaluation quality still depends heavily on good seeded telemetry
  scenarios

These are not weaknesses to hide. In a thesis defense, they are useful because
they show scope control and engineering realism.

## 7. Best Thesis Positioning

The most accurate and high-value project framing is:

> A real-time intelligent temperature-control platform that combines edge
> closed-loop execution, MQTT-based communication, time-series data ingestion,
> operator-facing monitoring, and AI-assisted parameter optimization with
> post-apply validation.

This framing is stronger than:

- "a dashboard"
- "an ESP32 simulation"
- "an AI recommendation toy"

because the implemented repository genuinely spans all of those pieces.

## 8. Best Defense Demonstration Value

For defense and demo planning, the highest-value chain already supported by the
current codebase is:

```text
abnormal control behavior
-> AI diagnosis
-> parameter recommendation
-> preview impact
-> MQTT apply
-> device ACK
-> actual telemetry comparison
-> recommendation effectiveness conclusion
```

This is the single most important story the repository can tell.

It shows:

- data acquisition
- system integration
- control understanding
- AI-assisted reasoning
- human-in-the-loop safety
- measurable outcome verification

That is the best path for an "excellent thesis" presentation.

## 9. Demo And Seed Script Inventory

Important runtime/demo helpers already present:

- [tdengine_live_feed.py](../scripts/tdengine_live_feed.py)
  synthetic telemetry for HMI live demos
- [mqtt_set_ack_loopback.py](../scripts/mqtt_set_ack_loopback.py)
  bridge-style `params/set -> params/ack` simulation and state writeback
- [mqtt_test_client.py](../scripts/mqtt_test_client.py)
  smoke test for telemetry / set / ack flow
- [data_hub_stress.py](../scripts/data_hub_stress.py)
  MQTT ingest/load testing tool
- [seed_post_apply_validation_demo.py](../scripts/seed_post_apply_validation_demo.py)
  ready-made post-apply validation scenarios
- [seed_recommendation_feedback_demo.py](../hmi/backend/ai/scripts/seed_recommendation_feedback_demo.py)
  recommendation feedback demo seeding

These scripts are not side notes.

They are the foundation of a stable thesis-defense demonstration because they
let the repository show value even when live edge behavior is partially
unstable.

## 10. Practical Reading Guide For Future Codex Sessions

If a future Codex session needs to rebuild context quickly, the fastest reading
order is:

1. [README.md](../README.md)
2. [simulator/wokwi/README.md](../simulator/wokwi/README.md)
3. [data-hub/README.md](../data-hub/README.md)
4. [hmi/README.md](../hmi/README.md)
5. [hmi/backend/ai/README.md](../hmi/backend/ai/README.md)
6. this file

Then move to these implementation anchors:

1. [edge_app.cpp](../simulator/wokwi/src/app/edge_app.cpp)
2. [ReactiveMqttConsumer.java](../data-hub/src/main/java/com/edgehub/datahub/mqtt/ReactiveMqttConsumer.java)
3. [MqttConsumePipeline.java](../data-hub/src/main/java/com/edgehub/datahub/pipeline/MqttConsumePipeline.java)
4. [devices.py](../hmi/backend/app/api/routes/devices.py)
5. [device-detail-page.tsx](../hmi/frontend/src/pages/device-detail-page.tsx)
6. [ai-page.tsx](../hmi/frontend/src/pages/ai-page.tsx)
7. [recommendation_service.py](../hmi/backend/app/services/ai/recommendation_service.py)
8. [recommendation_orchestrator.py](../hmi/backend/app/services/ai/recommendation_orchestrator.py)
9. [preview_simulator.py](../hmi/backend/app/services/ai/preview_simulator.py)
10. [post_effect_evaluator.py](../hmi/backend/app/services/ai/post_effect_evaluator.py)

## 11. Bottom-Line Summary

This project is best understood as a closed-loop intelligent temperature-control
platform with:

- a real edge runtime
- real MQTT integration
- real data-hub ingestion
- real HMI operations surface
- real AI-assisted recommendation logic
- real post-apply evaluation path

That is the mental model future work should preserve.

Documentation sync date: 2026-05-09.
