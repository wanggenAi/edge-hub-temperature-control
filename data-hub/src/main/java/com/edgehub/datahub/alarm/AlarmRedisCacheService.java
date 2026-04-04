package com.edgehub.datahub.alarm;

import com.edgehub.datahub.config.HubProperties;
import com.edgehub.datahub.model.DeviceStatusSnapshot;
import com.edgehub.datahub.model.ParsedHubMessage;
import com.edgehub.datahub.model.TelemetryPayload;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
@ConditionalOnProperty(prefix = "datahub.redis", name = "enabled", havingValue = "true")
public final class AlarmRedisCacheService {

  private static final Logger log = LoggerFactory.getLogger(AlarmRedisCacheService.class);
  private static final String RULES_HASH = "rules";

  private final HubProperties.Redis redisProperties;
  private final StringRedisTemplate redis;
  private final ObjectMapper objectMapper;

  public AlarmRedisCacheService(HubProperties properties, StringRedisTemplate redis, ObjectMapper objectMapper) {
    this.redisProperties = properties.getRedis();
    this.redis = redis;
    this.objectMapper = objectMapper;
  }

  @PostConstruct
  public void initRulesCache() {
    try {
      Map<String, RuleDefinition> defaults = defaultRules();
      String rulesKey = rulesKey();
      for (Map.Entry<String, RuleDefinition> entry : defaults.entrySet()) {
        if (Boolean.TRUE.equals(redis.opsForHash().hasKey(rulesKey, entry.getKey()))) {
          continue;
        }
        redis.opsForHash().put(rulesKey, entry.getKey(), objectMapper.writeValueAsString(entry.getValue()));
      }
      redis.expire(rulesKey, java.time.Duration.ofSeconds(Math.max(60L, redisProperties.getRulesTtlSeconds())));
      log.info("alarm redis rules cache initialized key={} size={}", rulesKey, defaults.size());
    } catch (Exception e) {
      log.warn("alarm redis rules cache init failed", e);
    }
  }

  public void onMessage(ParsedHubMessage message) {
    try {
      if (message instanceof ParsedHubMessage.TelemetryMessage telemetry) {
        onTelemetry(telemetry.topic().deviceId(), telemetry.receivedAt(), telemetry.payload());
      } else if (message instanceof ParsedHubMessage.ParameterAckMessage ack) {
        boolean active = !ack.payload().success();
        upsertActive(
            ack.topic().deviceId(),
            "param_apply_failed",
            active,
            "params_ack",
            active ? defaultReason("param_apply_failed") : "ack success",
            ack.receivedAt(),
            severityOf("param_apply_failed"));
      }
    } catch (Exception e) {
      log.warn("alarm redis cache update failed for message type={}", message.getClass().getSimpleName(), e);
    }
  }

  public void onDeviceStatus(DeviceStatusSnapshot status) {
    try {
      boolean active = !status.online();
      upsertActive(
          status.deviceId(),
          "device_offline",
          active,
          "device_status",
          active ? defaultReason("device_offline") : "device online",
          status.observedAt(),
          severityOf("device_offline"));
    } catch (Exception e) {
      log.warn("alarm redis cache update failed for device status device={}", status.deviceId(), e);
    }
  }

  private void onTelemetry(String deviceId, Instant observedAt, TelemetryPayload payload) {
    if (deviceId == null || deviceId.isBlank() || payload == null) {
      return;
    }

    double outBandThreshold = thresholdAsDouble("out_of_band", 0.5d);
    boolean outOfBand = Math.abs(payload.error_c()) > outBandThreshold;
    upsertActive(
        deviceId,
        "out_of_band",
        outOfBand,
        "rule_engine",
        outOfBand ? defaultReason("out_of_band") : "back in target band",
        observedAt,
        severityOf("out_of_band"));

    boolean sensorInvalid = payload.sensor_valid() != null && !payload.sensor_valid();
    upsertActive(
        deviceId,
        "sensor_invalid",
        sensorInvalid,
        "telemetry",
        sensorInvalid ? defaultReason("sensor_invalid") : "sensor valid",
        observedAt,
        severityOf("sensor_invalid"));

    double saturationThreshold = thresholdAsDouble("high_saturation", 85d);
    boolean highSaturation =
        payload.pwm_duty() >= saturationThreshold
            || "high".equalsIgnoreCase(payload.saturation_state())
            || "saturated".equalsIgnoreCase(payload.saturation_state());
    upsertActive(
        deviceId,
        "high_saturation",
        highSaturation,
        "telemetry",
        highSaturation ? defaultReason("high_saturation") : "saturation normal",
        observedAt,
        severityOf("high_saturation"));
  }

  private void upsertActive(
      String deviceId,
      String ruleCode,
      boolean active,
      String source,
      String reason,
      Instant observedAt,
      String severity) {
    if (deviceId == null || deviceId.isBlank()) {
      return;
    }
    String activeKey = activeKey(deviceId, ruleCode);
    String fsmKey = fsmKey(deviceId, ruleCode);
    String nowIso = observedAt == null ? Instant.now().toString() : observedAt.toString();

    Map<String, String> activeFields = new LinkedHashMap<>();
    activeFields.put("device_id", deviceId);
    activeFields.put("rule_code", ruleCode);
    activeFields.put("active", String.valueOf(active));
    activeFields.put("source", source);
    activeFields.put("reason", reason);
    activeFields.put("severity", severity);
    activeFields.put("updated_at", nowIso);
    if (!active) {
      activeFields.put("cleared_at", nowIso);
    }
    redis.opsForHash().putAll(activeKey, activeFields);
    redis.expire(activeKey, java.time.Duration.ofSeconds(Math.max(60L, redisProperties.getActiveTtlSeconds())));

    Map<String, String> fsmFields = new LinkedHashMap<>();
    fsmFields.put("device_id", deviceId);
    fsmFields.put("rule_code", ruleCode);
    fsmFields.put("active", String.valueOf(active));
    fsmFields.put("last_signal_at", nowIso);
    fsmFields.put("last_source", source);
    fsmFields.put("last_reason", reason);
    redis.opsForHash().putAll(fsmKey, fsmFields);
    redis.expire(fsmKey, java.time.Duration.ofSeconds(Math.max(60L, redisProperties.getFsmTtlSeconds())));
  }

  private double thresholdAsDouble(String ruleCode, double fallback) {
    RuleDefinition definition = ruleOf(ruleCode);
    if (definition == null || definition.threshold == null) {
      return fallback;
    }
    try {
      return Double.parseDouble(definition.threshold.trim());
    } catch (NumberFormatException ignored) {
      return fallback;
    }
  }

  private String severityOf(String ruleCode) {
    RuleDefinition definition = ruleOf(ruleCode);
    if (definition == null || definition.severity == null || definition.severity.isBlank()) {
      return "warning";
    }
    return definition.severity.toLowerCase(Locale.ROOT);
  }

  private String defaultReason(String ruleCode) {
    RuleDefinition definition = ruleOf(ruleCode);
    if (definition == null || definition.name == null || definition.name.isBlank()) {
      return ruleCode;
    }
    return definition.name;
  }

  private RuleDefinition ruleOf(String ruleCode) {
    Object raw = redis.opsForHash().get(rulesKey(), ruleCode);
    if (!(raw instanceof String value) || value.isBlank()) {
      return defaultRules().get(ruleCode);
    }
    try {
      return objectMapper.readValue(value, RuleDefinition.class);
    } catch (JsonProcessingException e) {
      return defaultRules().get(ruleCode);
    }
  }

  private String rulesKey() {
    return redisProperties.getAlarmKeyPrefix() + ":" + RULES_HASH;
  }

  private String activeKey(String deviceId, String ruleCode) {
    return redisProperties.getAlarmKeyPrefix() + ":active:" + deviceId + ":" + ruleCode;
  }

  private String fsmKey(String deviceId, String ruleCode) {
    return redisProperties.getAlarmKeyPrefix() + ":fsm:" + deviceId + ":" + ruleCode;
  }

  private Map<String, RuleDefinition> defaultRules() {
    Map<String, RuleDefinition> map = new LinkedHashMap<>();
    map.put("out_of_band", new RuleDefinition("Out of Band", "temperature_error", ">", "0.5", 30, "warning"));
    map.put("sensor_invalid", new RuleDefinition("Sensor Invalid", "sensor_valid", "==", "false", 10, "critical"));
    map.put("high_saturation", new RuleDefinition("High Saturation", "pwm_output", ">=", "85", 60, "warning"));
    map.put("param_apply_failed", new RuleDefinition("Param Apply Failed", "params_ack", "==", "failed", 5, "warning"));
    map.put("device_offline", new RuleDefinition("Device Offline", "telemetry_gap", ">", "60", 60, "critical"));
    return map;
  }

  public static final class RuleDefinition {
    public String name;
    public String target;
    public String operator;
    public String threshold;
    public Integer hold_seconds;
    public String severity;

    public RuleDefinition() {}

    public RuleDefinition(String name, String target, String operator, String threshold, Integer holdSeconds, String severity) {
      this.name = name;
      this.target = target;
      this.operator = operator;
      this.threshold = threshold;
      this.hold_seconds = holdSeconds;
      this.severity = severity;
    }
  }
}
