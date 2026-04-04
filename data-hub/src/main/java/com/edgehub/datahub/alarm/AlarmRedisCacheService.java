package com.edgehub.datahub.alarm;

import com.edgehub.datahub.config.HubProperties;
import com.edgehub.datahub.model.AlarmFactEvent;
import com.edgehub.datahub.model.DeviceStatusSnapshot;
import com.edgehub.datahub.model.ParsedHubMessage;
import com.edgehub.datahub.model.TelemetryPayload;
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
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
        if (redis.opsForHash().hasKey(rulesKey, entry.getKey())) {
          continue;
        }
        redis.opsForHash().put(rulesKey, entry.getKey(), objectMapper.writeValueAsString(entry.getValue()));
      }
      redis.expire(rulesKey, Duration.ofSeconds(Math.max(60L, redisProperties.getRulesTtlSeconds())));
      log.info("alarm redis rules cache initialized key={} size={}", rulesKey, defaults.size());
    } catch (Exception e) {
      log.warn("alarm redis rules cache init failed", e);
    }
  }

  public List<AlarmFactEvent> onMessage(ParsedHubMessage message) {
    List<AlarmFactEvent> emitted = new ArrayList<>();
    try {
      if (message instanceof ParsedHubMessage.TelemetryMessage telemetry) {
        emitted.addAll(onTelemetry(telemetry.topic().deviceId(), telemetry.receivedAt(), telemetry.payload()));
      } else if (message instanceof ParsedHubMessage.ParameterAckMessage ack) {
        boolean matched = !ack.payload().success();
        AlarmTransitionResult transition = processRuleSignal(
            ack.topic().deviceId(),
            "param_apply_failed",
            matched,
            "params_ack",
            matched ? defaultReason("param_apply_failed") : "ack success",
            ack.receivedAt(),
            severityOf("param_apply_failed"),
            null);
        if (transition.alarmEvent() != null) {
          emitted.add(transition.alarmEvent());
        }
      }
    } catch (Exception e) {
      log.warn("alarm redis cache update failed for message type={}", message.getClass().getSimpleName(), e);
    }
    return emitted;
  }

  public List<AlarmFactEvent> onDeviceStatus(DeviceStatusSnapshot status) {
    List<AlarmFactEvent> emitted = new ArrayList<>();
    try {
      boolean matched = !status.online();
      AlarmTransitionResult transition = processRuleSignal(
          status.deviceId(),
          "device_offline",
          matched,
          "device_status",
          matched ? defaultReason("device_offline") : "device online",
          status.observedAt(),
          severityOf("device_offline"),
          null);
      if (transition.alarmEvent() != null) {
        emitted.add(transition.alarmEvent());
      }
    } catch (Exception e) {
      log.warn("alarm redis cache update failed for device status device={}", status.deviceId(), e);
    }
    return emitted;
  }

  private List<AlarmFactEvent> onTelemetry(String deviceId, Instant observedAt, TelemetryPayload payload) {
    List<AlarmFactEvent> emitted = new ArrayList<>();
    if (deviceId == null || deviceId.isBlank() || payload == null) {
      return emitted;
    }

    double outBandThreshold = thresholdAsDouble("out_of_band", 0.5d);
    boolean outOfBand = Math.abs(payload.error_c()) > outBandThreshold;
    AlarmTransitionResult outBandResult = processRuleSignal(
        deviceId,
        "out_of_band",
        outOfBand,
        "rule_engine",
        outOfBand ? defaultReason("out_of_band") : "back in target band",
        observedAt,
        severityOf("out_of_band"),
        null);
    if (outBandResult.alarmEvent() != null) {
      emitted.add(outBandResult.alarmEvent());
    }

    boolean sensorInvalid = payload.sensor_valid() != null && !payload.sensor_valid();
    AlarmTransitionResult sensorResult = processRuleSignal(
        deviceId,
        "sensor_invalid",
        sensorInvalid,
        "telemetry",
        sensorInvalid ? defaultReason("sensor_invalid") : "sensor valid",
        observedAt,
        severityOf("sensor_invalid"),
        null);
    if (sensorResult.alarmEvent() != null) {
      emitted.add(sensorResult.alarmEvent());
    }

    double saturationThreshold = thresholdAsDouble("high_saturation", 85d);
    boolean highSaturation =
        payload.pwm_duty() >= saturationThreshold
            || "high".equalsIgnoreCase(payload.saturation_state())
            || "saturated".equalsIgnoreCase(payload.saturation_state());
    Map<String, Object> saturationContext = new LinkedHashMap<>();
    saturationContext.put("pwm_duty", payload.pwm_duty());
    saturationContext.put("threshold", saturationThreshold);
    AlarmTransitionResult saturationResult = processRuleSignal(
        deviceId,
        "high_saturation",
        highSaturation,
        "telemetry",
        highSaturation ? defaultReason("high_saturation") : "saturation normal",
        observedAt,
        severityOf("high_saturation"),
        saturationContext);
    if (saturationResult.alarmEvent() != null) {
      emitted.add(saturationResult.alarmEvent());
    }

    return emitted;
  }

  private AlarmTransitionResult processRuleSignal(
      String deviceId,
      String ruleCode,
      boolean signalMatched,
      String source,
      String reason,
      Instant observedAt,
      String severity,
      Map<String, Object> context) {
    if (deviceId == null || deviceId.isBlank()) {
      return AlarmTransitionResult.noop();
    }
    Instant observed = observedAt == null ? Instant.now() : observedAt;
    RuleDefinition rule = ruleOf(ruleCode);
    if (rule == null || Boolean.FALSE.equals(rule.enabled())) {
      return AlarmTransitionResult.noop();
    }

    int holdSeconds = Math.max(0, rule.hold_seconds() == null ? 0 : rule.hold_seconds());
    FsmStateSnapshot previous = loadFsmState(deviceId, ruleCode);
    FsmStateSnapshot next = previous.copy();

    next.deviceId = deviceId;
    next.ruleCode = ruleCode;
    next.lastSignalAt = observed;
    next.lastSource = source;
    next.lastReason = reason;

    AlarmFactEvent event = null;

    if (signalMatched) {
      if (previous.state == AlarmState.INACTIVE) {
        next.state = AlarmState.PENDING_ACTIVE;
        next.firstMatchAt = observed;
        next.firstClearCandidateAt = null;
        next.lastTransitionAt = observed;
      } else if (previous.state == AlarmState.PENDING_ACTIVE) {
        if (next.firstMatchAt == null) {
          next.firstMatchAt = observed;
          next.lastTransitionAt = observed;
        }
      } else if (previous.state == AlarmState.PENDING_CLEAR) {
        next.state = AlarmState.ACTIVE;
        next.firstClearCandidateAt = null;
        next.lastTransitionAt = observed;
      }

      if (next.state == AlarmState.PENDING_ACTIVE && elapsedSeconds(next.firstMatchAt, observed) >= holdSeconds) {
        next.state = AlarmState.ACTIVE;
        next.activeSince = previous.activeSince != null ? previous.activeSince : observed;
        next.lastTransitionAt = observed;
        event = buildTriggeredEvent(deviceId, ruleCode, severity, source, reason, observed, context);
      }
    } else {
      if (previous.state == AlarmState.ACTIVE) {
        next.state = AlarmState.PENDING_CLEAR;
        next.firstClearCandidateAt = observed;
        next.lastTransitionAt = observed;
      }
      if (previous.state == AlarmState.PENDING_ACTIVE) {
        next.state = AlarmState.INACTIVE;
        next.firstMatchAt = null;
        next.lastTransitionAt = observed;
      }
      if (next.state == AlarmState.PENDING_CLEAR) {
        if (next.firstClearCandidateAt == null) {
          next.firstClearCandidateAt = observed;
          next.lastTransitionAt = observed;
        }
        if (elapsedSeconds(next.firstClearCandidateAt, observed) >= holdSeconds) {
          next.state = AlarmState.INACTIVE;
          next.lastTransitionAt = observed;
          event = buildClearedEvent(deviceId, ruleCode, severity, source, reason, observed, previous.activeSince, context);
          next.activeSince = null;
          next.firstMatchAt = null;
          next.firstClearCandidateAt = null;
        }
      }
    }

    if (next.state == AlarmState.ACTIVE && next.activeSince == null) {
      next.activeSince = observed;
    }

    upsertActiveState(deviceId, ruleCode, next, signalMatched, source, reason, observed, severity);
    upsertFsmState(deviceId, ruleCode, next, source, reason, observed);

    return new AlarmTransitionResult(next, event);
  }

  private void upsertActiveState(
      String deviceId,
      String ruleCode,
      FsmStateSnapshot fsm,
      boolean signalMatched,
      String source,
      String reason,
      Instant observedAt,
      String severity) {
    String activeKey = activeKey(deviceId, ruleCode);
    Map<Object, Object> existing = redis.opsForHash().entries(activeKey);
    String existingTriggeredAt = stringValue(existing.get("triggered_at"));
    String nowIso = observedAt.toString();
    boolean isActive = fsm.state == AlarmState.ACTIVE || fsm.state == AlarmState.PENDING_CLEAR;

    Map<String, String> activeFields = new LinkedHashMap<>();
    activeFields.put("device_id", deviceId);
    activeFields.put("rule_code", ruleCode);
    activeFields.put("state", fsm.state.value);
    activeFields.put("active", Boolean.toString(isActive));
    activeFields.put("signal_matched", Boolean.toString(signalMatched));
    activeFields.put("source", source);
    activeFields.put("reason", reason);
    activeFields.put("severity", severity);
    activeFields.put("updated_at", nowIso);

    if (isActive) {
      String triggeredAt = existingTriggeredAt;
      if (fsm.activeSince != null) {
        triggeredAt = fsm.activeSince.toString();
      }
      if (triggeredAt == null || triggeredAt.isBlank()) {
        triggeredAt = nowIso;
      }
      activeFields.put("triggered_at", triggeredAt);
      activeFields.put("cleared_at", "");
    } else {
      if (existingTriggeredAt != null && !existingTriggeredAt.isBlank()) {
        activeFields.put("triggered_at", existingTriggeredAt);
      }
      activeFields.put("cleared_at", nowIso);
    }

    redis.opsForHash().putAll(activeKey, activeFields);
    redis.expire(activeKey, Duration.ofSeconds(Math.max(60L, redisProperties.getActiveTtlSeconds())));
  }

  private void upsertFsmState(
      String deviceId,
      String ruleCode,
      FsmStateSnapshot fsm,
      String source,
      String reason,
      Instant observedAt) {
    String fsmKey = fsmKey(deviceId, ruleCode);
    Map<String, String> fields = new LinkedHashMap<>();
    fields.put("device_id", deviceId);
    fields.put("rule_code", ruleCode);
    fields.put("state", fsm.state.value);
    putInstant(fields, "first_match_at", fsm.firstMatchAt);
    putInstant(fields, "first_clear_candidate_at", fsm.firstClearCandidateAt);
    putInstant(fields, "last_signal_at", observedAt);
    fields.put("last_source", source);
    fields.put("last_reason", reason);
    putInstant(fields, "active_since", fsm.activeSince);
    putInstant(fields, "last_transition_at", fsm.lastTransitionAt);

    redis.opsForHash().putAll(fsmKey, fields);
    redis.expire(fsmKey, Duration.ofSeconds(Math.max(60L, redisProperties.getFsmTtlSeconds())));
  }

  private FsmStateSnapshot loadFsmState(String deviceId, String ruleCode) {
    Map<Object, Object> map = redis.opsForHash().entries(fsmKey(deviceId, ruleCode));
    FsmStateSnapshot snapshot = new FsmStateSnapshot();
    snapshot.deviceId = deviceId;
    snapshot.ruleCode = ruleCode;
    snapshot.state = AlarmState.from(stringValue(map.get("state")));
    snapshot.firstMatchAt = instantOf(stringValue(map.get("first_match_at")));
    snapshot.firstClearCandidateAt = instantOf(stringValue(map.get("first_clear_candidate_at")));
    snapshot.lastSignalAt = instantOf(stringValue(map.get("last_signal_at")));
    snapshot.lastSource = stringValue(map.get("last_source"));
    snapshot.lastReason = stringValue(map.get("last_reason"));
    snapshot.activeSince = instantOf(stringValue(map.get("active_since")));
    snapshot.lastTransitionAt = instantOf(stringValue(map.get("last_transition_at")));
    return snapshot;
  }

  private AlarmFactEvent buildTriggeredEvent(
      String deviceId,
      String ruleCode,
      String severity,
      String source,
      String reason,
      Instant eventTime,
      Map<String, Object> context) {
    return new AlarmFactEvent(
        deviceId,
        ruleCode,
        severity,
        source,
        reason,
        "triggered",
        eventTime,
        eventTime,
        null,
        toContextJson(context));
  }

  private AlarmFactEvent buildClearedEvent(
      String deviceId,
      String ruleCode,
      String severity,
      String source,
      String reason,
      Instant eventTime,
      Instant triggeredAt,
      Map<String, Object> context) {
    Long durationSeconds = null;
    if (triggeredAt != null) {
      durationSeconds = Math.max(0L, Duration.between(triggeredAt, eventTime).getSeconds());
    }
    return new AlarmFactEvent(
        deviceId,
        ruleCode,
        severity,
        source,
        reason,
        "cleared",
        eventTime,
        triggeredAt,
        durationSeconds,
        toContextJson(context));
  }

  private long elapsedSeconds(Instant start, Instant end) {
    if (start == null || end == null) {
      return 0L;
    }
    long seconds = Duration.between(start, end).getSeconds();
    return Math.max(0L, seconds);
  }

  private String toContextJson(Map<String, Object> context) {
    if (context == null || context.isEmpty()) {
      return null;
    }
    try {
      return objectMapper.writeValueAsString(context);
    } catch (JsonProcessingException e) {
      log.debug("alarm context serialization failed", e);
      return null;
    }
  }

  private void putInstant(Map<String, String> fields, String key, Instant value) {
    fields.put(key, value == null ? "" : value.toString());
  }

  private Instant instantOf(String value) {
    if (value == null || value.isBlank()) {
      return null;
    }
    try {
      return Instant.parse(value);
    } catch (Exception ignored) {
      return null;
    }
  }

  private String stringValue(Object value) {
    if (value == null) {
      return null;
    }
    String text = value.toString();
    return text.isBlank() ? null : text;
  }

  private double thresholdAsDouble(String ruleCode, double fallback) {
    RuleDefinition definition = ruleOf(ruleCode);
    if (definition == null || definition.threshold() == null) {
      return fallback;
    }
    try {
      return Double.parseDouble(definition.threshold().trim());
    } catch (NumberFormatException ignored) {
      return fallback;
    }
  }

  private String severityOf(String ruleCode) {
    RuleDefinition definition = ruleOf(ruleCode);
    if (definition == null || definition.severity() == null || definition.severity().isBlank()) {
      return "warning";
    }
    return definition.severity().toLowerCase(Locale.ROOT);
  }

  private String defaultReason(String ruleCode) {
    RuleDefinition definition = ruleOf(ruleCode);
    if (definition == null || definition.name() == null || definition.name().isBlank()) {
      return ruleCode;
    }
    return definition.name();
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
    map.put("out_of_band", new RuleDefinition("Out of Band", "temperature_error", ">", "0.5", 30, "warning", true));
    map.put("sensor_invalid", new RuleDefinition("Sensor Invalid", "sensor_valid", "==", "false", 10, "critical", true));
    map.put("high_saturation", new RuleDefinition("High Saturation", "pwm_output", ">=", "85", 60, "warning", true));
    map.put("param_apply_failed", new RuleDefinition("Param Apply Failed", "params_ack", "==", "failed", 5, "warning", true));
    map.put("device_offline", new RuleDefinition("Device Offline", "telemetry_gap", ">", "60", 60, "critical", true));
    return map;
  }

  private enum AlarmState {
    INACTIVE("inactive"),
    PENDING_ACTIVE("pending_active"),
    ACTIVE("active"),
    PENDING_CLEAR("pending_clear");

    private final String value;

    AlarmState(String value) {
      this.value = value;
    }

    private static AlarmState from(String value) {
      if (value == null || value.isBlank()) {
        return INACTIVE;
      }
      for (AlarmState state : values()) {
        if (state.value.equalsIgnoreCase(value)) {
          return state;
        }
      }
      return INACTIVE;
    }
  }

  private static final class FsmStateSnapshot {
    private String deviceId;
    private String ruleCode;
    private AlarmState state = AlarmState.INACTIVE;
    private Instant firstMatchAt;
    private Instant firstClearCandidateAt;
    private Instant lastSignalAt;
    private String lastSource;
    private String lastReason;
    private Instant activeSince;
    private Instant lastTransitionAt;

    private FsmStateSnapshot copy() {
      FsmStateSnapshot copy = new FsmStateSnapshot();
      copy.deviceId = deviceId;
      copy.ruleCode = ruleCode;
      copy.state = state;
      copy.firstMatchAt = firstMatchAt;
      copy.firstClearCandidateAt = firstClearCandidateAt;
      copy.lastSignalAt = lastSignalAt;
      copy.lastSource = lastSource;
      copy.lastReason = lastReason;
      copy.activeSince = activeSince;
      copy.lastTransitionAt = lastTransitionAt;
      return copy;
    }
  }

  private record AlarmTransitionResult(FsmStateSnapshot state, AlarmFactEvent alarmEvent) {
    private static AlarmTransitionResult noop() {
      return new AlarmTransitionResult(new FsmStateSnapshot(), null);
    }
  }

  @JsonIgnoreProperties(ignoreUnknown = true)
  public record RuleDefinition(
      String name,
      String target,
      String operator,
      String threshold,
      @JsonAlias({"holdSeconds"}) Integer hold_seconds,
      String severity,
      Boolean enabled) {}
}
