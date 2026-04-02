package com.edgehub.datahub.storage;

import com.edgehub.datahub.config.HubProperties;
import com.edgehub.datahub.model.ParameterAckPayload;
import com.edgehub.datahub.model.ParameterSetPayload;
import com.edgehub.datahub.model.ParsedHubMessage;
import com.edgehub.datahub.model.TelemetryPayload;
import com.edgehub.datahub.model.TelemetrySteadySummary;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Component
@ConditionalOnProperty(prefix = "datahub.storage", name = "mode", havingValue = "tdengine-rest")
public final class TdengineRestWriter implements TdengineWriter {

  private static final Logger log = LoggerFactory.getLogger(TdengineRestWriter.class);

  private final HubProperties.Tdengine properties;
  private final ObjectMapper objectMapper;
  private final HttpClient httpClient;
  private final String authorizationHeader;
  private final String databaseName;
  private final URI sqlEndpoint;
  private final Mono<Void> ensureInitialized;
  private final AtomicBoolean initializedLogged = new AtomicBoolean();

  public TdengineRestWriter(HubProperties hubProperties, ObjectMapper objectMapper) {
    this.properties = hubProperties.getStorage().getTdengine();
    this.objectMapper = objectMapper;
    this.httpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(properties.getConnectTimeoutSeconds()))
        .build();
    this.databaseName = identifier(properties.getDatabase());
    this.authorizationHeader = "Basic " + Base64.getEncoder().encodeToString(
        (properties.getUsername() + ":" + properties.getPassword()).getBytes(StandardCharsets.UTF_8));
    this.sqlEndpoint = URI.create(normalizeBaseUrl(properties.getUrl()) + "/rest/sql");
    this.ensureInitialized = Mono.defer(this::initializeSchema)
        .subscribeOn(Schedulers.boundedElastic())
        .cache();
  }

  @Override
  public Mono<Void> writeTelemetry(ParsedHubMessage.TelemetryMessage telemetry) {
    String tableName = tableName("telemetry", telemetry.topic().deviceId());
    String sql = "INSERT INTO " + qualifiedTableName(tableName)
        + " USING " + qualifiedTableName("telemetry")
        + " TAGS (" + stringValue(telemetry.topic().deviceId()) + ", " + stringValue(telemetry.topic().rawTopic()) + ")"
        + " (ts, uptime_ms, target_temp_c, sim_temp_c, sensor_temp_c, error_c, integral_error, control_output, pwm_duty, pwm_norm, control_period_ms, saturation_state, sensor_valid, run_id, control_mode, controller_version, kp, ki, kd, system_state, has_pending_params, pending_params_age_ms)"
        + " VALUES ("
        + telemetry.receivedAt().toEpochMilli() + ", "
        + telemetry.payload().uptime_ms() + ", "
        + numericValue(telemetry.payload().target_temp_c()) + ", "
        + numericValue(telemetry.payload().sim_temp_c()) + ", "
        + numericValue(telemetry.payload().sensor_temp_c()) + ", "
        + numericValue(telemetry.payload().error_c()) + ", "
        + numericValue(telemetry.payload().integral_error()) + ", "
        + numericValue(telemetry.payload().control_output()) + ", "
        + telemetry.payload().pwm_duty() + ", "
        + numericValue(telemetry.payload().pwm_norm()) + ", "
        + telemetry.payload().control_period_ms() + ", "
        + stringValue(telemetry.payload().saturation_state()) + ", "
        + booleanValue(telemetry.payload().sensor_valid()) + ", "
        + stringValue(telemetry.payload().run_id()) + ", "
        + stringValue(telemetry.payload().control_mode()) + ", "
        + stringValue(telemetry.payload().controller_version()) + ", "
        + numericValue(telemetry.payload().kp()) + ", "
        + numericValue(telemetry.payload().ki()) + ", "
        + numericValue(telemetry.payload().kd()) + ", "
        + stringValue(telemetry.payload().system_state()) + ", "
        + booleanValue(telemetry.payload().has_pending_params()) + ", "
        + telemetry.payload().pending_params_age_ms()
        + ")";
    String logMessage = "tdengine.telemetry_written device=%s runId=%s table=%s uptimeMs=%s targetTemp=%s simTemp=%s sensorTemp=%s controlPeriodMs=%s saturationState=%s sensorValid=%s"
        .formatted(
            telemetry.topic().deviceId(),
            telemetry.payload().run_id(),
            qualifiedTableName(tableName),
            telemetry.payload().uptime_ms(),
            telemetry.payload().target_temp_c(),
            telemetry.payload().sim_temp_c(),
            telemetry.payload().sensor_temp_c(),
            telemetry.payload().control_period_ms(),
            telemetry.payload().saturation_state(),
            telemetry.payload().sensor_valid());
    return executeWrite(sql, "telemetry", telemetry.topic().deviceId(), logMessage);
  }

  @Override
  public Mono<Void> writeTelemetrySummary(TelemetrySteadySummary summary) {
    String tableName = tableName("telemetry_summary", summary.deviceId());
    String sql = "INSERT INTO " + qualifiedTableName(tableName)
        + " USING " + qualifiedTableName("telemetry_summary")
        + " TAGS (" + stringValue(summary.deviceId()) + ", " + stringValue(summary.rawTopic()) + ")"
        + " (ts, run_id, window_start_ts, window_end_ts, duration_ms, flush_reason, sample_count, control_period_ms, uptime_start_ms, uptime_end_ms, target_temp_avg, sim_temp_avg, sensor_temp_avg, sensor_temp_min, sensor_temp_max, error_avg, abs_error_avg, abs_error_max, control_output_avg, control_output_min, control_output_max, pwm_duty_avg, pwm_duty_min, pwm_duty_max, pwm_norm_avg, pwm_norm_min, pwm_norm_max, control_mode, system_state, kp, ki, kd)"
        + " VALUES ("
        + summary.windowEnd().toEpochMilli() + ", "
        + stringValue(summary.runId()) + ", "
        + summary.windowStart().toEpochMilli() + ", "
        + summary.windowEnd().toEpochMilli() + ", "
        + summary.durationMs() + ", "
        + stringValue(summary.flushReason()) + ", "
        + summary.sampleCount() + ", "
        + summary.controlPeriodMs() + ", "
        + summary.uptimeStartMs() + ", "
        + summary.uptimeEndMs() + ", "
        + numericValue(summary.targetTempAvg()) + ", "
        + numericValue(summary.simTempAvg()) + ", "
        + numericValue(summary.sensorTempAvg()) + ", "
        + numericValue(summary.sensorTempMin()) + ", "
        + numericValue(summary.sensorTempMax()) + ", "
        + numericValue(summary.errorAvg()) + ", "
        + numericValue(summary.absErrorAvg()) + ", "
        + numericValue(summary.absErrorMax()) + ", "
        + numericValue(summary.controlOutputAvg()) + ", "
        + numericValue(summary.controlOutputMin()) + ", "
        + numericValue(summary.controlOutputMax()) + ", "
        + numericValue(summary.pwmDutyAvg()) + ", "
        + summary.pwmDutyMin() + ", "
        + summary.pwmDutyMax() + ", "
        + numericValue(summary.pwmNormAvg()) + ", "
        + numericValue(summary.pwmNormMin()) + ", "
        + numericValue(summary.pwmNormMax()) + ", "
        + stringValue(summary.controlMode()) + ", "
        + stringValue(summary.systemState()) + ", "
        + numericValue(summary.kp()) + ", "
        + numericValue(summary.ki()) + ", "
        + numericValue(summary.kd())
        + ")";
    String logMessage =
        "tdengine.telemetry_summary_written device=%s runId=%s table=%s samples=%s durationMs=%s controlPeriodMs=%s sensorTempAvg=%s absErrorMax=%s pwmDutyRange=%s-%s flushReason=%s"
            .formatted(
                summary.deviceId(),
                summary.runId(),
                qualifiedTableName(tableName),
                summary.sampleCount(),
                summary.durationMs(),
                summary.controlPeriodMs(),
                summary.sensorTempAvg(),
                summary.absErrorMax(),
                summary.pwmDutyMin(),
                summary.pwmDutyMax(),
                summary.flushReason());
    return executeWrite(sql, "telemetry_summary", summary.deviceId(), logMessage);
  }

  @Override
  public Mono<Void> writeParameterSet(ParsedHubMessage.ParameterSetMessage parameterSet) {
    ParameterSetPayload payload = parameterSet.payload();
    String tableName = tableName("params_set", parameterSet.topic().deviceId());
    String sql = "INSERT INTO " + qualifiedTableName(tableName)
        + " USING " + qualifiedTableName("params_set")
        + " TAGS (" + stringValue(parameterSet.topic().deviceId()) + ", " + stringValue(parameterSet.topic().rawTopic()) + ")"
        + " VALUES ("
        + parameterSet.receivedAt().toEpochMilli() + ", "
        + numericValue(payload.target_temp_c()) + ", "
        + numericValue(payload.kp()) + ", "
        + numericValue(payload.ki()) + ", "
        + numericValue(payload.kd()) + ", "
        + numericValue(payload.control_period_ms()) + ", "
        + stringValue(payload.control_mode()) + ", "
        + booleanValue(payload.apply_immediately())
        + ")";
    String logMessage = "tdengine.params_set_written device=%s table=%s targetTemp=%s kp=%s ki=%s controlMode=%s"
        .formatted(
            parameterSet.topic().deviceId(),
            qualifiedTableName(tableName),
            payload.target_temp_c(),
            payload.kp(),
            payload.ki(),
            payload.control_mode());
    return executeWrite(sql, "params_set", parameterSet.topic().deviceId(), logMessage);
  }

  @Override
  public Mono<Void> writeParameterAck(ParsedHubMessage.ParameterAckMessage parameterAck) {
    ParameterAckPayload payload = parameterAck.payload();
    String tableName = tableName("params_ack", parameterAck.topic().deviceId());
    String sql = "INSERT INTO " + qualifiedTableName(tableName)
        + " USING " + qualifiedTableName("params_ack")
        + " TAGS (" + stringValue(parameterAck.topic().deviceId()) + ", " + stringValue(parameterAck.topic().rawTopic()) + ")"
        + " VALUES ("
        + parameterAck.receivedAt().toEpochMilli() + ", "
        + stringValue(payload.ack_type()) + ", "
        + booleanValue(payload.success()) + ", "
        + booleanValue(payload.applied_immediately()) + ", "
        + booleanValue(payload.has_pending_params()) + ", "
        + numericValue(payload.target_temp_c()) + ", "
        + numericValue(payload.kp()) + ", "
        + numericValue(payload.ki()) + ", "
        + numericValue(payload.kd()) + ", "
        + payload.control_period_ms() + ", "
        + stringValue(payload.control_mode()) + ", "
        + stringValue(payload.reason()) + ", "
        + payload.uptime_ms()
        + ")";
    String logMessage = "tdengine.params_ack_written device=%s table=%s ackType=%s success=%s reason=%s"
        .formatted(
            parameterAck.topic().deviceId(),
            qualifiedTableName(tableName),
            payload.ack_type(),
            payload.success(),
            payload.reason());
    return executeWrite(sql, "params_ack", parameterAck.topic().deviceId(), logMessage);
  }

  private Mono<Void> executeWrite(String sql, String eventType, String deviceId, String successLogMessage) {
    return ensureInitialized.then(Mono.fromRunnable(() -> executeSql(sql))
        .subscribeOn(Schedulers.boundedElastic())
        .doOnSuccess(ignored -> {
          if (properties.isLogEachWrite()) {
            log.info(successLogMessage);
          } else {
            log.debug("tdengine {} persisted device={}", eventType, deviceId);
          }
        })
        .then());
  }

  private Mono<Void> initializeSchema() {
    return Mono.fromRunnable(() -> {
      if (properties.isAutoCreate()) {
        executeSql("CREATE DATABASE IF NOT EXISTS " + databaseName + " PRECISION 'ms'");
      }
      List<String> ddl = List.of(
          """
          CREATE STABLE IF NOT EXISTS %s.telemetry (
            ts TIMESTAMP,
            uptime_ms BIGINT,
            target_temp_c DOUBLE,
            sim_temp_c DOUBLE,
            sensor_temp_c DOUBLE,
            error_c DOUBLE,
            integral_error DOUBLE,
            control_output DOUBLE,
            pwm_duty INT,
            pwm_norm DOUBLE,
            control_period_ms BIGINT,
            saturation_state VARCHAR(32),
            sensor_valid BOOL,
            run_id VARCHAR(128),
            control_mode VARCHAR(64),
            controller_version VARCHAR(64),
            kp DOUBLE,
            ki DOUBLE,
            kd DOUBLE,
            system_state VARCHAR(64),
            has_pending_params BOOL,
            pending_params_age_ms BIGINT
          ) TAGS (
            device_id BINARY(128),
            mqtt_topic BINARY(255)
          )
          """.formatted(databaseName),
          """
          CREATE STABLE IF NOT EXISTS %s.telemetry_summary (
            ts TIMESTAMP,
            run_id VARCHAR(128),
            window_start_ts TIMESTAMP,
            window_end_ts TIMESTAMP,
            duration_ms BIGINT,
            flush_reason VARCHAR(64),
            sample_count INT,
            control_period_ms BIGINT,
            uptime_start_ms BIGINT,
            uptime_end_ms BIGINT,
            target_temp_avg DOUBLE,
            sim_temp_avg DOUBLE,
            sensor_temp_avg DOUBLE,
            sensor_temp_min DOUBLE,
            sensor_temp_max DOUBLE,
            error_avg DOUBLE,
            abs_error_avg DOUBLE,
            abs_error_max DOUBLE,
            control_output_avg DOUBLE,
            control_output_min DOUBLE,
            control_output_max DOUBLE,
            pwm_duty_avg DOUBLE,
            pwm_duty_min INT,
            pwm_duty_max INT,
            pwm_norm_avg DOUBLE,
            pwm_norm_min DOUBLE,
            pwm_norm_max DOUBLE,
            control_mode VARCHAR(64),
            system_state VARCHAR(64),
            kp DOUBLE,
            ki DOUBLE,
            kd DOUBLE
          ) TAGS (
            device_id BINARY(128),
            mqtt_topic BINARY(255)
          )
          """.formatted(databaseName),
          """
          CREATE STABLE IF NOT EXISTS %s.params_set (
            ts TIMESTAMP,
            target_temp_c DOUBLE,
            kp DOUBLE,
            ki DOUBLE,
            kd DOUBLE,
            control_period_ms BIGINT,
            control_mode VARCHAR(64),
            apply_immediately BOOL
          ) TAGS (
            device_id BINARY(128),
            mqtt_topic BINARY(255)
          )
          """.formatted(databaseName),
          """
          CREATE STABLE IF NOT EXISTS %s.params_ack (
            ts TIMESTAMP,
            ack_type VARCHAR(64),
            success BOOL,
            applied_immediately BOOL,
            has_pending_params BOOL,
            target_temp_c DOUBLE,
            kp DOUBLE,
            ki DOUBLE,
            kd DOUBLE,
            control_period_ms BIGINT,
            control_mode VARCHAR(64),
            reason VARCHAR(255),
            uptime_ms BIGINT
          ) TAGS (
            device_id BINARY(128),
            mqtt_topic BINARY(255)
          )
          """.formatted(databaseName));
      ddl.forEach(this::executeSql);
      ensureTelemetrySchemaCompatibility();
      ensureTelemetrySummarySchemaCompatibility();
      if (initializedLogged.compareAndSet(false, true)) {
        log.info(
            "tdengine rest writer initialized url={} database={} autoCreate={}",
            properties.getUrl(),
            properties.getDatabase(),
            properties.isAutoCreate());
      }
    }).then();
  }

  private void executeSql(String sql) {
    executeSqlForResponse(sql);
  }

  private JsonNode executeSqlForResponse(String sql) {
    HttpRequest request = HttpRequest.newBuilder(sqlEndpoint)
        .timeout(Duration.ofSeconds(properties.getRequestTimeoutSeconds()))
        .header("Content-Type", "text/plain; charset=UTF-8")
        .header("Authorization", authorizationHeader)
        .POST(HttpRequest.BodyPublishers.ofString(sql, StandardCharsets.UTF_8))
        .build();
    try {
      HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
      if (response.statusCode() < 200 || response.statusCode() >= 300) {
        throw new IllegalStateException("tdengine http status " + response.statusCode() + " body=" + response.body());
      }
      JsonNode payload = objectMapper.readTree(response.body());
      int code = payload.path("code").asInt(-1);
      if (code != 0) {
        throw new IllegalStateException("tdengine code=" + code + " desc=" + payload.path("desc").asText());
      }
      return payload;
    } catch (InterruptedException exception) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException("tdengine request failed", exception);
    } catch (IOException exception) {
      throw new IllegalStateException("tdengine request failed", exception);
    }
  }

  private void ensureTelemetrySchemaCompatibility() {
    ensureColumnExists("telemetry", "control_period_ms", "BIGINT");
    ensureColumnExists("telemetry", "saturation_state", "VARCHAR(32)");
    ensureColumnExists("telemetry", "sensor_valid", "BOOL");
    ensureColumnExists("telemetry", "run_id", "VARCHAR(128)");
  }

  private void ensureTelemetrySummarySchemaCompatibility() {
    ensureColumnExists("telemetry_summary", "run_id", "VARCHAR(128)");
    ensureColumnExists("telemetry_summary", "control_period_ms", "BIGINT");
  }

  private void ensureColumnExists(String stableName, String columnName, String columnDefinition) {
    if (stableHasColumn(stableName, columnName)) {
      return;
    }
    executeSql("ALTER STABLE " + qualifiedTableName(stableName) + " ADD COLUMN " + columnName + " " + columnDefinition);
  }

  private boolean stableHasColumn(String stableName, String columnName) {
    JsonNode response = executeSqlForResponse("DESCRIBE " + qualifiedTableName(stableName));
    for (JsonNode row : response.path("data")) {
      if (row.isArray() && row.size() > 0 && columnName.equalsIgnoreCase(row.get(0).asText())) {
        return true;
      }
    }
    return false;
  }

  private String tableName(String prefix, String deviceId) {
    return identifier(prefix + "_" + sanitizeIdentifier(deviceId));
  }

  private String qualifiedTableName(String tableName) {
    return databaseName + "." + tableName;
  }

  private String identifier(String value) {
    return sanitizeIdentifier(value);
  }

  private String sanitizeIdentifier(String value) {
    String normalized = value.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9_]", "_");
    if (normalized.isBlank()) {
      return "unknown";
    }
    if (Character.isDigit(normalized.charAt(0))) {
      return "t_" + normalized;
    }
    return normalized;
  }

  private String stringValue(String value) {
    if (value == null) {
      return "NULL";
    }
    return "'" + value.replace("'", "''") + "'";
  }

  private String numericValue(Number value) {
    return value == null ? "NULL" : value.toString();
  }

  private String booleanValue(Boolean value) {
    return value == null ? "NULL" : Boolean.TRUE.equals(value) ? "true" : "false";
  }

  private String normalizeBaseUrl(String url) {
    return url.endsWith("/") ? url.substring(0, url.length() - 1) : url;
  }
}
