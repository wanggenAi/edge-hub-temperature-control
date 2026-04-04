# Java Data Hub Layer

This module is the Java data hub baseline for the project.

It is one of the three active modules in the current repository baseline:

- edge simulation: `simulator/wokwi`
- data ingestion and storage: `data-hub` (this module)
- application layer: `hmi`

Documentation sync date: 2026-04-04.

## Runtime Baseline

This module is pinned to:

- JDK `17`
- Spring Boot `3.4.x`
- Log4j2 via Spring Boot starter
- Gradle Wrapper (`gradlew`) as the preferred entry
- Gradle `8.x` only needed once when generating the wrapper locally

Check Java locally:

```bash
java -version
```

The output should show Java 17, for example:

```bash
openjdk version "17..."
```

Current scope:

- subscribe to MQTT telemetry / params/set / params/ack
- parse payloads into stable Java models
- process messages through a Reactor pipeline
- apply bounded backpressure controls between MQTT ingress and downstream processing
- hand off normalized data to a TDengine-oriented writer abstraction
- optionally archive normalized events into local JSONL files for inspection and replay

Current non-goals:

- HMI
- web API
- control command entry
- optimizer logic
- microservice splitting

Run assumptions:

- MQTT broker is already available
- current payloads follow the Wokwi edge node structure
- TDengine can be provided locally through Docker
- local file archival can be used as the current persistence baseline

Suggested environment variables:

- `DATAHUB_MQTT_URI` default: `tcp://127.0.0.1:1883`
- `DATAHUB_MQTT_CLIENT_ID` default: `java-data-hub-v1`
- `DATAHUB_MQTT_USERNAME` optional
- `DATAHUB_MQTT_PASSWORD` optional
- `DATAHUB_MQTT_QOS` default: `1`
- `DATAHUB_MQTT_MAX_INFLIGHT` default: `128`
- `DATAHUB_MQTT_LOG_EACH_MESSAGE` default: `true`
- `DATAHUB_BUFFER_SIZE` default: `2048`
- `DATAHUB_PROCESSING_CONCURRENCY` default: `8`
- `DATAHUB_PROCESSING_PARSER_CONCURRENCY` default: `8`
- `DATAHUB_PROCESSING_WRITER_CONCURRENCY` default: `8`
- `DATAHUB_PROCESSING_PREFETCH` default: `256`
- `DATAHUB_BACKPRESSURE_SOURCE_QUEUE_SIZE` default: `2048`
- `DATAHUB_BACKPRESSURE_PIPELINE_BUFFER_SIZE` default: `4096`
- `DATAHUB_BACKPRESSURE_OVERFLOW_STRATEGY` default: `drop_oldest`
- `DATAHUB_STORAGE_MODE` default: `log`
- `DATAHUB_STORAGE_BASE_DIR` default: `runtime/data-hub`
- `DATAHUB_STORAGE_TDENGINE_URL` default: `http://127.0.0.1:6041`
- `DATAHUB_STORAGE_TDENGINE_DATABASE` default: `edgehub`
- `DATAHUB_STORAGE_TDENGINE_USERNAME` default: `root`
- `DATAHUB_LOGGING_LEVEL_ROOT` default: `info`
- `DATAHUB_LOGGING_LEVEL_APP` default: `info`
- `DATAHUB_LOGGING_LEVEL_SPRING` default: `warn`
- `DATAHUB_LOGGING_LEVEL_MQTT` default: `warn`
- `DATAHUB_LOGGING_DIR` default: `runtime/logs`

## Local Properties File

Tracked template:

`config/application.example.properties`

Local file to create on your machine only:

`config/application.properties`

This local file is ignored by Git.

Suggested setup:

```bash
cd data-hub
cp config/application.example.properties config/application.properties
```

The application loads configuration with this priority:

1. environment variables
2. `config/application.properties`
3. built-in defaults

## MQTT Consumption And Backpressure

The current data hub uses a bounded two-stage flow:

- ingress queue at the MQTT callback boundary
- pipeline buffer before parse and persist stages

Current design goals:

- avoid losing messages just because the MQTT client connected slightly before the Reactor subscriber attached
- keep buffering bounded instead of allowing unbounded heap growth
- make overload behavior explicit and configurable
- log parse failures, persist failures, and overflow drops with enough context for debugging

Key tuning properties:

- `datahub.mqtt.qos`
- `datahub.mqtt.max-inflight`
- `datahub.mqtt.log-each-message`
- `datahub.processing.parser-concurrency`
- `datahub.processing.writer-concurrency`
- `datahub.processing.prefetch`
- `datahub.backpressure.source-queue-size`
- `datahub.backpressure.pipeline-buffer-size`
- `datahub.backpressure.overflow-strategy`
- `datahub.backpressure.overflow-log-every`
- `datahub.telemetry-filter.enabled`
- `datahub.telemetry-filter.heartbeat-interval-ms`
- `datahub.telemetry-filter.state-ttl-ms`
- `datahub.telemetry-filter.max-active-devices`
- `datahub.telemetry-summary.enabled`
- `datahub.telemetry-summary.min-samples`
- `datahub.telemetry-summary.idle-flush-interval-ms`
- `datahub.telemetry-summary.idle-flush-check-ms`
- `datahub.telemetry-summary.window-ttl-ms`
- `datahub.telemetry-summary.max-active-windows`
- `datahub.device-status.enabled`
- `datahub.device-status.online-timeout-ms`
- `datahub.device-status.offline-check-ms`
- `datahub.device-status.state-ttl-ms`
- `datahub.device-status.max-active-devices`
- `datahub.monitoring.stats-log-enabled`
- `datahub.monitoring.stats-log-interval-ms`

Supported overflow strategies:

- `drop_oldest`
- `drop_latest`
- `error`

`datahub.mqtt.max-inflight` limits how many QoS-managed messages can remain in the MQTT client's in-flight window at the same time. This is one of the key protocol-level controls for keeping the consumer stable under burst traffic.

`datahub.mqtt.log-each-message=true` makes the MQTT ingress layer print every received message with topic, QoS, retained flag, and payload. This is useful during integration because it lets you confirm the edge node is still publishing exactly what the data hub is consuming.

## Runtime Stats

The data hub emits a periodic summary log to help tune the consumer pipeline under load.

Example fields:

- `recv`
  - inbound MQTT messages accepted by the callback layer
- `ingressDrop`
  - messages dropped before entering the Reactor pipeline
- `pipelineDrop`
  - messages dropped by the Reactor backpressure buffer
- `parseFail`
  - messages that reached the parser but could not be parsed
- `persistFail`
  - messages that parsed successfully but failed during persistence
- `telemetrySkip`
  - telemetry messages intentionally skipped by the steady-state filter because they did not add enough new information yet
- `telemetryOk`
  - telemetry messages persisted successfully
- `telemetrySummaryOk`
  - compact steady-state summary rows persisted after skipped windows are aggregated
- `paramsSetOk`
  - parameter-set messages persisted successfully
- `paramsAckOk`
  - parameter-ack messages persisted successfully
- `filterSize`
  - current number of active device filter states kept in the cache
- `filterEvict`
  - number of filter states evicted by TTL or size protection
- `summarySize`
  - current number of active summary windows kept in the cache
- `summaryEvict`
  - number of summary windows evicted by TTL or size protection
- `summaryDiscard`
  - summary windows dropped because they were too short to persist
- `deviceStatusOk`
  - device online/offline status events persisted successfully
- `deviceStatusSize`
  - current number of active device presence states kept in memory
- `deviceStatusEvict`
  - number of device presence states evicted by TTL or size protection

Use these stats together with:

- `maxInflight`
- `sourceQueue`
- `pipelineBuffer`
- `parserConcurrency`
- `writerConcurrency`
- `prefetch`
- `overflow`

## Telemetry Persistence Filtering

To avoid filling TDengine with low-value steady-state repeats, the data hub can filter telemetry before persistence while still keeping the raw MQTT ingest path unchanged.

Current behavior when `datahub.telemetry-filter.enabled=true`:

- the first telemetry point for each device is always written
- telemetry is written again when meaningful values change beyond configured deadbands
- telemetry is force-written on heartbeat interval even if values stay steady
- parameter-set and parameter-ack events reset the device filter state so the next telemetry sample is written again

Recommended starting properties:

- `datahub.telemetry-filter.enabled=true`
- `datahub.telemetry-filter.heartbeat-interval-ms=30000`
- `datahub.telemetry-filter.state-ttl-ms=900000`
- `datahub.telemetry-filter.max-active-devices=100000`
- `datahub.telemetry-filter.target-temp-deadband=0.05`
- `datahub.telemetry-filter.sim-temp-deadband=0.05`
- `datahub.telemetry-filter.sensor-temp-deadband=0.05`
- `datahub.telemetry-filter.error-deadband=0.02`
- `datahub.telemetry-filter.control-output-deadband=1.0`
- `datahub.telemetry-filter.pwm-duty-deadband=1`
- `datahub.telemetry-filter.parameter-deadband=0.01`

This keeps transition data dense while making long steady-state periods much lighter.

## Telemetry Steady-State Summaries

Filtering alone reduces write volume, but by itself it also hides how long the system stayed stable and how much the actuator drifted during that quiet period.

To keep that information useful for later analysis, the data hub can aggregate skipped telemetry into compact summary rows.

Current behavior when `datahub.telemetry-summary.enabled=true`:

- skipped telemetry points are accumulated per device
- when a heartbeat write happens, or a meaningful change resumes, the skipped window is flushed as one summary row
- if a device goes quiet while a summary window is still open, the window is also flushed after the configured idle timeout
- short windows below `datahub.telemetry-summary.min-samples` are ignored

Recommended starting properties:

- `datahub.telemetry-summary.enabled=true`
- `datahub.telemetry-summary.min-samples=3`
- `datahub.telemetry-summary.idle-flush-interval-ms=45000`
- `datahub.telemetry-summary.idle-flush-check-ms=10000`
- `datahub.telemetry-summary.window-ttl-ms=120000`
- `datahub.telemetry-summary.max-active-windows=100000`

Each summary row captures the kind of features that are more useful than raw repeats:

- stable-period duration
- sample count
- average sensor temperature
- average and max absolute error
- control output average and range
- pwm duty average and range
- final control mode and system state

This is valuable because it preserves steady-state behavior without storing every repeated point, which is much friendlier for later model training and control-tuning analysis.

## Device Online And Offline Tracking

The data hub can also maintain per-device online state so the HMI can show whether a device is currently reachable.

Current behavior when `datahub.device-status.enabled=true`:

- the first telemetry or parameter-ack seen from a device marks it online
- a reconnect after timeout writes a new online event
- telemetry `system_state` changes also write a new online event
- if no telemetry or parameter-ack arrives within the configured timeout, the device is marked offline
- device presence state is also bounded with TTL and maximum active device count so the tracker cannot grow without limit

Recommended starting properties:

- `datahub.device-status.enabled=true`
- `datahub.device-status.online-timeout-ms=60000`
- `datahub.device-status.offline-check-ms=10000`
- `datahub.device-status.state-ttl-ms=86400000`
- `datahub.device-status.max-active-devices=100000`

## Storage Modes

The writer is now selected by configuration:

- `datahub.storage.mode=log`
  - default
  - keeps the current behavior and logs normalized records
- `datahub.storage.mode=file`
  - writes normalized events into JSON Lines files under `datahub.storage.base-dir`
- `datahub.storage.mode=tdengine-rest`
  - writes normalized events into TDengine through the REST SQL endpoint
  - can auto-create the target database and supertables on startup

When `file` mode is enabled, the module creates:

- `telemetry.jsonl`
- `params-set.jsonl`
- `params-ack.jsonl`
- `device-status.jsonl`

Each line is a self-contained normalized event envelope with:

- `event_type`
- `device_id`
- `received_at`
- `topic`
- `payload`

## Logging

The module uses `log4j2-spring.xml` with values sourced from `config/application.properties`.

Default behavior:

- write to console and rolling file simultaneously
- rotate daily and also on file size threshold
- compress archived logs as `.gz`
- clean archives by retention days and total archive size

Key properties:

- `spring.application.name`
- `logging.config`
- `datahub.logging.level.root`
- `datahub.logging.level.app`
- `datahub.logging.level.spring`
- `datahub.logging.level.mqtt`
- `datahub.logging.dir`
- `datahub.logging.file-name`
- `datahub.logging.archive-dir`
- `datahub.logging.pattern`
- `datahub.logging.rolling.file-pattern`
- `datahub.logging.rolling.max-file-size`
- `datahub.logging.rolling.retention-days`
- `datahub.logging.rolling.total-size-cap`

## TDengine REST Writer

The TDengine writer uses the REST SQL endpoint and supports:

- automatic database creation
- automatic supertable creation for telemetry / params_set / params_ack
- per-device subtables derived from `device_id`

Key properties:

- `datahub.storage.tdengine.url`
- `datahub.storage.tdengine.database`
- `datahub.storage.tdengine.username`
- `datahub.storage.tdengine.password`
- `datahub.storage.tdengine.auto-create`
- `datahub.storage.tdengine.log-each-write`
- `datahub.storage.tdengine.connect-timeout-seconds`
- `datahub.storage.tdengine.request-timeout-seconds`

Recommended local deployment reference:

- `../docs/deployment/tdengine-docker-local.md`

Verified local workflow:

1. start TDengine with Docker Compose
2. set `datahub.storage.mode=tdengine-rest`
3. start `data-hub`
4. confirm the log line:
   `tdengine rest writer initialized ...`
5. watch per-write logs such as:
   `tdengine.telemetry_written ...`
6. verify rows with:

```bash
docker exec edgehub-tdengine taos -s "SHOW DATABASES; USE edgehub; SHOW STABLES; SHOW TABLES; SELECT COUNT(*) FROM edgehub.telemetry_edge_node_001;"
```

## Build and Run With Gradle Wrapper

Preferred commands after the wrapper exists:

```bash
cd data-hub
./gradlew clean build
./gradlew bootRun
```

If the wrapper has not been generated yet, install Gradle once and run:

```bash
cd data-hub
gradle wrapper
```

Then use:

```bash
cd data-hub
./gradlew clean build
./gradlew bootRun
```

## Minimal Run Requirements

Before starting the module, make sure:

1. JDK 17 is active
2. `gradlew` exists in the module, or Gradle is installed once to generate it
3. the MQTT broker is reachable
4. if using `file` mode, the configured archive directory is writable
5. if using `tdengine-rest` mode, TDengine REST must be reachable on the configured URL

Example:

```bash
cd data-hub
./gradlew bootRun
```
