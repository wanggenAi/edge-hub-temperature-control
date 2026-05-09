# End-to-End Architecture Overview

## 1. Architectural Goal

This project targets an intelligent constant-temperature control scenario. The
current repository is organized as an end-to-end engineering platform rather
than as a single controller demo.

The architecture is designed to make five concerns clear and independently
verifiable:

1. Edge control execution
2. MQTT communication
3. Data ingestion and time-series persistence
4. HMI operation and observability
5. AI-assisted decision support and feedback learning

This separation keeps the control loop explainable, keeps integration behavior
observable, and gives the thesis a complete system story: sensing, control,
communication, storage, decision support, and validation.

## 2. Runtime Flow

The main implemented runtime path is:

```text
ESP32 edge node / Wokwi simulation
-> MQTT telemetry
-> Java data-hub ingest, parse, backpressure, and persistence
-> TDengine / PostgreSQL backed HMI views
-> AI recommendation generation and preview
-> MQTT params/set dispatch
-> edge params/ack
-> post-apply telemetry validation and feedback samples
```

This means the repository supports a closed engineering loop, not only one-way
monitoring.

## 3. Edge Control Layer

Main location:

- `simulator/wokwi`

Main responsibilities:

- acquire temperature data
- execute local PI/PID-compatible control logic
- generate PWM output
- maintain runtime control parameters
- publish structured telemetry
- receive `params/set` messages
- publish `params/ack` messages
- expose safety and connectivity status in telemetry

Current implementation baseline:

- ESP32-oriented PlatformIO project
- Wokwi simulation profile and real-hardware build profile
- DS18B20 input abstraction
- PWM actuator abstraction
- bounded-integral PI controller with PID-compatible `kd` field
- virtual thermal model for repeatable demonstration and experiments
- MQTT telemetry, parameter downlink, and ACK handling

Engineering value:

- the edge side is a runnable closed-loop node abstraction
- runtime parameter updates can be exercised through MQTT
- telemetry contains enough status fields for reliability and safety discussion

## 4. MQTT Communication Layer

Main references:

- `docs/mqtt_interface.md`
- `simulator/wokwi/src/comms/mqtt/`
- `hmi/backend/app/services/mqtt_publisher.py`
- `data-hub/src/main/java/com/edgehub/datahub/mqtt/`

Implemented message flows:

- `edge/temperature/<device_id>/telemetry`
- `edge/temperature/<device_id>/params/set`
- `edge/temperature/<device_id>/params/ack`
- `edgehub/config/alarm-rules/updated`
- `edgehub/config/storage-rules/updated`

Engineering value:

- telemetry, command intent, and command result are separated
- HMI apply actions can wait for device ACK instead of assuming success
- Data Hub can persist both control intent and device response for traceability

## 5. Data Hub Layer

Main location:

- `data-hub`

Main responsibilities:

- subscribe to MQTT telemetry, `params/set`, `params/ack`, and config topics
- normalize payloads into typed Java models
- apply bounded ingress and processing backpressure
- persist events into TDengine or file/log storage
- aggregate steady-state telemetry summaries
- track device online/offline status
- expose runtime metrics for Ops Console and tuning

Current implementation baseline:

- Java 17 + Spring Boot
- HiveMQ MQTT client
- Reactor processing pipeline
- configurable overflow strategy and concurrency
- TDengine REST writer with auto-created supertables
- Prometheus/Actuator runtime metrics

Engineering value:

- this layer demonstrates system reliability, scalability, and operations depth
- it turns MQTT messages into durable experimental and operational data
- it gives the AI and HMI layers a stable data foundation

## 6. HMI And Operations Layer

Main location:

- `hmi`

Main responsibilities:

- authenticate users and enforce RBAC
- manage devices, parameters, alarms, and storage rules
- visualize current state, history, alarms, and control performance
- publish parameter updates through MQTT
- surface Data Hub, runtime, AI, and learning-loop health

Current implementation baseline:

- FastAPI backend
- React + TypeScript frontend
- PostgreSQL relational control plane
- TDengine-backed telemetry/history reads
- admin/operator/viewer roles
- device detail, history, alarms, storage rules, AI, and Ops pages

Engineering value:

- the HMI is the operator control plane, not only a visualization page
- it connects human decisions to runtime MQTT actions
- it gives the project a practical engineering/product surface for defense demo

## 7. AI Decision Support Layer

Main locations:

- `hmi/backend/app/services/ai`
- `hmi/backend/ai/scripts`
- `hmi/frontend/src/pages/ai-page.tsx`

Main responsibilities:

- extract control-performance features from telemetry
- classify current control problems
- generate PID parameter recommendations
- optionally rank candidate recommendations with trained artifacts
- preview the expected effect before apply
- evaluate actual post-apply effect from real telemetry
- feed control-action results into offline learning datasets

Current implementation baseline:

- feature extraction
- rule-based multi-problem classifier
- rule-based PID tuning engine
- optional model-based recommendation ranking
- preview simulator
- post-effect evaluator
- standalone AI runtime service with backend fallback
- model lifecycle and learning-loop observability

Engineering value:

- the strongest AI claim is explainable decision support, not unsafe full
autonomy
- the system supports human-in-the-loop optimization
- preview and post-apply validation make recommendations measurable instead of
purely decorative

## 8. Offline Learning And Feedback Pipeline

Main locations:

- `ml`
- `hmi/backend/ai/scripts`
- `hmi/backend/app/services/control_action_learning.py`

Main responsibilities:

- export TDengine data to parquet
- build cleaned training windows
- extract features and pseudo labels
- export control-action feedback samples
- train recommendation-success and preview-gap models
- record model lifecycle runs and active artifacts

Engineering value:

- the project has a data-to-model iteration path
- AI behavior can improve from recommendation outcomes
- demo data and training data are connected to real runtime entities

## 9. Thesis-Friendly Summary

A concise architecture statement for the thesis defense:

> This system implements an intelligent temperature-control platform that
> combines edge closed-loop control, MQTT communication, Java-based data
> ingestion, time-series storage, HMI operations, and AI-assisted PID parameter
> optimization with pre-apply preview and post-apply validation.

The most valuable demonstration chain is:

```text
abnormal telemetry
-> AI diagnosis
-> recommendation
-> preview simulation
-> MQTT apply
-> device ACK
-> actual telemetry comparison
-> effectiveness conclusion
```

Documentation sync date: 2026-05-09.
