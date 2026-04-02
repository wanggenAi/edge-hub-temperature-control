# Java Data Hub Layer

This module is the Java data hub baseline for the project.

## Runtime Baseline

This module is pinned to:

- JDK `17`
- Spring Boot `3.4.x`
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
- hand off normalized data to a TDengine-oriented writer abstraction

Current non-goals:

- HMI
- web API
- control command entry
- optimizer logic
- microservice splitting

Run assumptions:

- MQTT broker is already available
- current payloads follow the Wokwi edge node structure
- TDengine integration is still abstracted behind `TdengineWriter`

Suggested environment variables:

- `DATA_HUB_MQTT_URI` default: `tcp://127.0.0.1:1883`
- `DATA_HUB_MQTT_CLIENT_ID` default: `java-data-hub-v1`
- `DATA_HUB_MQTT_USERNAME` optional
- `DATA_HUB_MQTT_PASSWORD` optional
- `DATA_HUB_BUFFER_SIZE` default: `2048`

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

Example:

```bash
cd data-hub
./gradlew bootRun
```
