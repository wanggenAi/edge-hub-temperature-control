package com.edgehub.datahub.alarm;

import com.edgehub.datahub.config.HubProperties;
import com.edgehub.datahub.model.AlarmFactEvent;
import com.edgehub.datahub.model.DeviceStatusSnapshot;
import com.edgehub.datahub.model.ParsedHubMessage;
import com.edgehub.datahub.model.TelemetryPayload;
import com.edgehub.datahub.rules.AlarmRuleDefinition;
import com.edgehub.datahub.rules.RuleConfigService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public final class AlarmRuleEngineService {

  private static final Logger log = LoggerFactory.getLogger(AlarmRuleEngineService.class);

  private final RuleConfigService ruleConfigService;
  private final ObjectMapper objectMapper;
  private final Cache<String, FsmStateSnapshot> fsmStateByDeviceRule;

  public AlarmRuleEngineService(HubProperties properties, RuleConfigService ruleConfigService, ObjectMapper objectMapper) {
    this.ruleConfigService = ruleConfigService;
    this.objectMapper = objectMapper;
    this.fsmStateByDeviceRule = Caffeine.newBuilder()
        .maximumSize(500_000)
        .expireAfterAccess(Duration.ofMillis(Math.max(60_000L, properties.getRuleStore().getAlarmStateTtlMs())))
        .build();
  }

  public List<AlarmFactEvent> onMessage(ParsedHubMessage message) {
    List<AlarmFactEvent> emitted = new ArrayList<>();
    try {
      if (message instanceof ParsedHubMessage.TelemetryMessage telemetry) {
        emitted.addAll(onTelemetry(telemetry.topic().deviceId(), telemetry.receivedAt(), telemetry.payload()));
      } else if (message instanceof ParsedHubMessage.ParameterAckMessage ack) {
        boolean matched = !ack.payload().success();
        Map<String, Object> ackContext = new LinkedHashMap<>();
        ackContext.put("ack_type", ack.payload().ack_type());
        ackContext.put("reason", ack.payload().reason());
        ackContext.put("fault_latched", ack.payload().fault_latched());
        ackContext.put("fault_reason", ack.payload().fault_reason());
        AlarmTransitionResult transition = processRuleSignal(
            ack.topic().deviceId(),
            "param_apply_failed",
            matched,
            "params_ack",
            matched ? defaultReason("param_apply_failed") : "ack success",
            ack.receivedAt(),
            severityOf("param_apply_failed"),
            ackContext);
        if (transition.alarmEvent() != null) {
          emitted.add(transition.alarmEvent());
        }
      }
    } catch (Exception exception) {
      log.warn("alarm rule engine update failed messageType={}", message.getClass().getSimpleName(), exception);
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
    } catch (Exception exception) {
      log.warn("alarm rule engine update failed device={}", status.deviceId(), exception);
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
        Map.of("error_c", payload.error_c(), "threshold", outBandThreshold));
    if (outBandResult.alarmEvent() != null) {
      emitted.add(outBandResult.alarmEvent());
    }

    boolean sensorInvalid = (payload.sensor_valid() != null && !payload.sensor_valid())
        || (payload.sensor_status() != null && !"ok".equalsIgnoreCase(payload.sensor_status()));
    Map<String, Object> sensorContext = new LinkedHashMap<>();
    sensorContext.put("sensor_valid", payload.sensor_valid());
    sensorContext.put("sensor_status", payload.sensor_status());
    sensorContext.put("sensor_temp_c", payload.sensor_temp_c());
    AlarmTransitionResult sensorResult = processRuleSignal(
        deviceId,
        "sensor_invalid",
        sensorInvalid,
        "telemetry",
        sensorInvalid ? defaultReason("sensor_invalid") : "sensor valid",
        observedAt,
        severityOf("sensor_invalid"),
        sensorContext);
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

    boolean faultLatched = Boolean.TRUE.equals(payload.fault_latched());
    Map<String, Object> faultContext = new LinkedHashMap<>();
    faultContext.put("fault_latched", payload.fault_latched());
    faultContext.put("fault_reason", payload.fault_reason());
    faultContext.put("software_max_safe_temp_c", payload.software_max_safe_temp_c());
    AlarmTransitionResult faultLatchedResult = processRuleSignal(
        deviceId,
        "fault_latched",
        faultLatched,
        "safety",
        faultLatched ? defaultReason("fault_latched") : "fault latch cleared",
        observedAt,
        severityOf("fault_latched"),
        faultContext);
    if (faultLatchedResult.alarmEvent() != null) {
      emitted.add(faultLatchedResult.alarmEvent());
    }

    boolean forcedOff = Boolean.TRUE.equals(payload.safety_output_forced_off());
    Map<String, Object> forcedOffContext = new LinkedHashMap<>();
    forcedOffContext.put("safety_output_forced_off", payload.safety_output_forced_off());
    forcedOffContext.put("fault_reason", payload.fault_reason());
    AlarmTransitionResult forcedOffResult = processRuleSignal(
        deviceId,
        "safety_output_forced_off",
        forcedOff,
        "safety",
        forcedOff ? defaultReason("safety_output_forced_off") : "safety output released",
        observedAt,
        severityOf("safety_output_forced_off"),
        forcedOffContext);
    if (forcedOffResult.alarmEvent() != null) {
      emitted.add(forcedOffResult.alarmEvent());
    }

    boolean maxSafeExceeded = false;
    if (payload.sensor_temp_c() != null && payload.software_max_safe_temp_c() != null) {
      maxSafeExceeded = payload.sensor_temp_c() > payload.software_max_safe_temp_c();
    }
    Map<String, Object> maxSafeContext = new LinkedHashMap<>();
    maxSafeContext.put("sensor_temp_c", payload.sensor_temp_c());
    maxSafeContext.put("software_max_safe_temp_c", payload.software_max_safe_temp_c());
    AlarmTransitionResult maxSafeResult = processRuleSignal(
        deviceId,
        "max_safe_temp_exceeded",
        maxSafeExceeded,
        "safety",
        maxSafeExceeded ? defaultReason("max_safe_temp_exceeded") : "temperature below software max safe threshold",
        observedAt,
        severityOf("max_safe_temp_exceeded"),
        maxSafeContext);
    if (maxSafeResult.alarmEvent() != null) {
      emitted.add(maxSafeResult.alarmEvent());
    }

    long dtErrorAbs = Math.abs(payload.dt_error_ms() == null ? 0L : payload.dt_error_ms());
    double dtThresholdMs = thresholdAsDouble("control_dt_deviation", 200d);
    boolean dtDeviation = dtErrorAbs >= dtThresholdMs;
    Map<String, Object> dtContext = new LinkedHashMap<>();
    dtContext.put("actual_dt_ms", payload.actual_dt_ms());
    dtContext.put("dt_error_ms", payload.dt_error_ms());
    dtContext.put("threshold_ms", dtThresholdMs);
    AlarmTransitionResult dtDeviationResult = processRuleSignal(
        deviceId,
        "control_dt_deviation",
        dtDeviation,
        "control_loop",
        dtDeviation ? defaultReason("control_dt_deviation") : "control dt recovered",
        observedAt,
        severityOf("control_dt_deviation"),
        dtContext);
    if (dtDeviationResult.alarmEvent() != null) {
      emitted.add(dtDeviationResult.alarmEvent());
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

    AlarmRuleDefinition rule = ruleOf(ruleCode);
    if (rule == null || Boolean.FALSE.equals(rule.enabled())) {
      return AlarmTransitionResult.noop();
    }

    Instant observed = observedAt == null ? Instant.now() : observedAt;
    int holdSeconds = Math.max(0, rule.holdSeconds() == null ? 0 : rule.holdSeconds());

    String key = fsmKey(deviceId, ruleCode);
    FsmStateSnapshot previous = fsmStateByDeviceRule.getIfPresent(key);
    if (previous == null) {
      previous = new FsmStateSnapshot();
      previous.deviceId = deviceId;
      previous.ruleCode = ruleCode;
    }
    FsmStateSnapshot next = previous.copy();
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
    fsmStateByDeviceRule.put(key, next);
    return new AlarmTransitionResult(next, event);
  }

  private String fsmKey(String deviceId, String ruleCode) {
    return deviceId + ":" + ruleCode;
  }

  private long elapsedSeconds(Instant start, Instant end) {
    if (start == null || end == null) {
      return 0L;
    }
    long seconds = Duration.between(start, end).getSeconds();
    return Math.max(0L, seconds);
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

  private double thresholdAsDouble(String ruleCode, double fallback) {
    AlarmRuleDefinition definition = ruleOf(ruleCode);
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
    AlarmRuleDefinition definition = ruleOf(ruleCode);
    if (definition == null || definition.severity() == null || definition.severity().isBlank()) {
      return "warning";
    }
    return definition.severity().toLowerCase(Locale.ROOT);
  }

  private String defaultReason(String ruleCode) {
    AlarmRuleDefinition definition = ruleOf(ruleCode);
    if (definition == null || definition.name() == null || definition.name().isBlank()) {
      return ruleCode;
    }
    return definition.name();
  }

  private AlarmRuleDefinition ruleOf(String ruleCode) {
    return ruleConfigService.resolveAlarmRule(ruleCode);
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
      return new AlarmTransitionResult(null, null);
    }
  }
}
