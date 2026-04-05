package com.edgehub.datahub.rules;

import com.edgehub.datahub.config.HubProperties;
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import jakarta.annotation.PostConstruct;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

@Service
public final class RuleConfigService {

  public static final String ALARM_RULES_UPDATED_TOPIC = "edgehub/config/alarm-rules/updated";
  public static final String STORAGE_RULES_UPDATED_TOPIC = "edgehub/config/storage-rules/updated";

  private static final Logger log = LoggerFactory.getLogger(RuleConfigService.class);

  private final HubProperties properties;
  private final Cache<String, AlarmRuleDefinition> alarmRulesByCode;
  private final Cache<String, StorageRuleDefinition> storageRulesByScope;
  private final Cache<String, StorageRuleDefinition> resolvedStorageByDevice;
  private final AtomicLong configVersion = new AtomicLong(0L);

  public RuleConfigService(HubProperties properties) {
    this.properties = properties;
    this.alarmRulesByCode = Caffeine.newBuilder().maximumSize(512).build();
    this.storageRulesByScope = Caffeine.newBuilder().maximumSize(2048).build();
    this.resolvedStorageByDevice = Caffeine.newBuilder()
        .maximumSize(200_000)
        .expireAfterWrite(Duration.ofMinutes(5))
        .build();
  }

  @PostConstruct
  public void init() {
    refreshAll("startup");
  }

  @Scheduled(
      initialDelayString = "${datahub.rule-store.refresh-interval-ms:300000}",
      fixedDelayString = "${datahub.rule-store.refresh-interval-ms:300000}")
  public void scheduledRefresh() {
    refreshAll("scheduled");
  }

  public boolean onConfigTopic(String topic, String payload) {
    if (!ALARM_RULES_UPDATED_TOPIC.equals(topic) && !STORAGE_RULES_UPDATED_TOPIC.equals(topic)) {
      return false;
    }
    refreshAll("mqtt:" + topic);
    return true;
  }

  public AlarmRuleDefinition resolveAlarmRule(String ruleCode) {
    AlarmRuleDefinition configured = alarmRulesByCode.getIfPresent(ruleCode);
    if (configured != null) {
      return configured;
    }
    return defaultAlarmRules().get(ruleCode);
  }

  public StorageRuleDefinition resolveStorageRule(String deviceId) {
    String key = deviceId == null || deviceId.isBlank() ? "*" : deviceId;
    StorageRuleDefinition cached = resolvedStorageByDevice.getIfPresent(key);
    if (cached != null) {
      return cached;
    }

    StorageRuleDefinition resolved = null;
    if (deviceId != null && !deviceId.isBlank()) {
      StorageRuleDefinition deviceRule = storageRulesByScope.getIfPresent(scopeKey("device", deviceId));
      if (deviceRule != null && deviceRule.enabled()) {
        resolved = applyRawModeDefaults(deviceRule);
      }
    }
    if (resolved == null) {
      StorageRuleDefinition globalRule = storageRulesByScope.getIfPresent(scopeKey("global", "*"));
      if (globalRule != null && globalRule.enabled()) {
        resolved = applyRawModeDefaults(globalRule);
      }
    }
    if (resolved == null) {
      resolved = defaultStorageRule();
    }

    resolvedStorageByDevice.put(key, resolved);
    return resolved;
  }

  public long version() {
    return configVersion.get();
  }

  private void refreshAll(String reason) {
    if (!properties.getRuleStore().isEnabled()) {
      loadDefaultsOnly(reason);
      return;
    }

    Map<String, AlarmRuleDefinition> alarmLoaded = new LinkedHashMap<>();
    Map<String, StorageRuleDefinition> storageLoaded = new LinkedHashMap<>();

    try (Connection connection = openConnection()) {
      loadAlarmRules(connection, alarmLoaded);
      loadStorageRules(connection, storageLoaded);
    } catch (SQLException exception) {
      log.warn("rule-store refresh failed reason={} message={}", reason, exception.getMessage());
      if (alarmRulesByCode.estimatedSize() == 0 && storageRulesByScope.estimatedSize() == 0) {
        loadDefaultsOnly(reason + ":fallback");
      }
      return;
    }

    if (alarmLoaded.isEmpty()) {
      alarmLoaded.putAll(defaultAlarmRules());
    }
    if (storageLoaded.isEmpty()) {
      StorageRuleDefinition fallback = defaultStorageRule();
      storageLoaded.put(scopeKey(fallback.scopeType(), fallback.scopeValue()), fallback);
    }

    alarmRulesByCode.invalidateAll();
    alarmRulesByCode.putAll(alarmLoaded);

    storageRulesByScope.invalidateAll();
    storageRulesByScope.putAll(storageLoaded);

    resolvedStorageByDevice.invalidateAll();

    long version = configVersion.incrementAndGet();
    log.info(
        "rule-store refreshed reason={} version={} alarmRules={} storageRules={}",
        reason,
        version,
        alarmLoaded.size(),
        storageLoaded.size());
    if (STORAGE_RULES_UPDATED_TOPIC.equals(reason.replace("mqtt:", ""))) {
      logStorageRuleSnapshot(version, storageLoaded);
    }
  }

  private void loadDefaultsOnly(String reason) {
    Map<String, AlarmRuleDefinition> alarmDefaults = defaultAlarmRules();
    StorageRuleDefinition storageDefault = defaultStorageRule();

    alarmRulesByCode.invalidateAll();
    alarmRulesByCode.putAll(alarmDefaults);

    storageRulesByScope.invalidateAll();
    storageRulesByScope.put(scopeKey(storageDefault.scopeType(), storageDefault.scopeValue()), storageDefault);

    resolvedStorageByDevice.invalidateAll();

    long version = configVersion.incrementAndGet();
    log.info(
        "rule-store loaded defaults reason={} version={} alarmRules={} storageRules=1",
        reason,
        version,
        alarmDefaults.size());
  }

  private Connection openConnection() throws SQLException {
    DriverManager.setLoginTimeout(Math.max(1, properties.getRuleStore().getConnectTimeoutSeconds()));
    return DriverManager.getConnection(
        properties.getRuleStore().getJdbcUrl(),
        properties.getRuleStore().getUsername(),
        properties.getRuleStore().getPassword());
  }

  private void loadAlarmRules(Connection connection, Map<String, AlarmRuleDefinition> out) throws SQLException {
    String sql = """
        SELECT rule_code, name, target, operator, threshold, hold_seconds, severity, enabled, scope_type, scope_value
        FROM alarm_rules
        """;
    try (Statement statement = connection.createStatement(); ResultSet rs = statement.executeQuery(sql)) {
      while (rs.next()) {
        String ruleCode = text(rs.getString("rule_code"));
        if (ruleCode == null || ruleCode.isBlank()) {
          continue;
        }
        out.put(
            ruleCode,
            new AlarmRuleDefinition(
                ruleCode,
                text(rs.getString("name")),
                text(rs.getString("target")),
                text(rs.getString("operator")),
                text(rs.getString("threshold")),
                rs.getObject("hold_seconds") == null ? 0 : rs.getInt("hold_seconds"),
                text(rs.getString("severity")),
                rs.getObject("enabled") == null || rs.getBoolean("enabled"),
                text(rs.getString("scope_type")),
                text(rs.getString("scope_value"))));
      }
    }
  }

  private void loadStorageRules(Connection connection, Map<String, StorageRuleDefinition> out) throws SQLException {
    String sql = """
        SELECT id, scope_type, scope_value, raw_mode, summary_enabled, summary_min_samples, heartbeat_interval_ms,
               target_temp_deadband, sim_temp_deadband, sensor_temp_deadband, error_deadband,
               integral_error_deadband, control_output_deadband, pwm_duty_deadband, pwm_norm_deadband,
               parameter_deadband, enabled
        FROM storage_rules
        """;
    try (Statement statement = connection.createStatement(); ResultSet rs = statement.executeQuery(sql)) {
      while (rs.next()) {
        String scopeType = normalizeScopeType(rs.getString("scope_type"));
        String scopeValue = text(rs.getString("scope_value"));
        if (scopeValue == null || scopeValue.isBlank()) {
          scopeValue = "*";
        }
        StorageRuleDefinition loaded = new StorageRuleDefinition(
            rs.getObject("id") == null ? null : rs.getLong("id"),
            scopeType,
            scopeValue,
            normalizeRawMode(rs.getString("raw_mode")),
            rs.getObject("summary_enabled") == null || rs.getBoolean("summary_enabled"),
            Math.max(1, rs.getObject("summary_min_samples") == null ? 3 : rs.getInt("summary_min_samples")),
            Math.max(0L, rs.getObject("heartbeat_interval_ms") == null ? 30000L : rs.getLong("heartbeat_interval_ms")),
            Math.max(0d, rs.getObject("target_temp_deadband") == null ? 0.05d : rs.getDouble("target_temp_deadband")),
            Math.max(0d, rs.getObject("sim_temp_deadband") == null ? 0.05d : rs.getDouble("sim_temp_deadband")),
            Math.max(0d, rs.getObject("sensor_temp_deadband") == null ? 0.05d : rs.getDouble("sensor_temp_deadband")),
            Math.max(0d, rs.getObject("error_deadband") == null ? 0.02d : rs.getDouble("error_deadband")),
            Math.max(0d, rs.getObject("integral_error_deadband") == null ? 1.0d : rs.getDouble("integral_error_deadband")),
            Math.max(0d, rs.getObject("control_output_deadband") == null ? 1.0d : rs.getDouble("control_output_deadband")),
            Math.max(0, (int) Math.round(rs.getObject("pwm_duty_deadband") == null ? 1d : rs.getDouble("pwm_duty_deadband"))),
            Math.max(0d, rs.getObject("pwm_norm_deadband") == null ? 0.01d : rs.getDouble("pwm_norm_deadband")),
            Math.max(0d, rs.getObject("parameter_deadband") == null ? 0.01d : rs.getDouble("parameter_deadband")),
            rs.getObject("enabled") == null || rs.getBoolean("enabled"));
        out.put(scopeKey(scopeType, scopeValue), applyRawModeDefaults(loaded));
      }
    }
  }

  private String scopeKey(String scopeType, String scopeValue) {
    return normalizeScopeType(scopeType) + ":" + (scopeValue == null || scopeValue.isBlank() ? "*" : scopeValue);
  }

  private String normalizeScopeType(String value) {
    if (value == null) {
      return "global";
    }
    String normalized = value.toLowerCase(Locale.ROOT).trim();
    return "device".equals(normalized) ? "device" : "global";
  }

  private String normalizeRawMode(String value) {
    if (value == null || value.isBlank()) {
      return "full";
    }
    String normalized = value.toLowerCase(Locale.ROOT).trim();
    return switch (normalized) {
      case "disabled", "strict", "relaxed" -> normalized;
      default -> "full";
    };
  }

  private String text(String value) {
    return value == null ? null : value.trim();
  }

  private void logStorageRuleSnapshot(long version, Map<String, StorageRuleDefinition> storageLoaded) {
    if (storageLoaded.isEmpty()) {
      log.info("rule-store storage snapshot version={} empty", version);
      return;
    }
    storageLoaded.values().forEach(rule -> log.info(
        "storage-rule effective version={} scope={}:{} rawMode={} enabled={} summaryEnabled={} summaryMinSamples={} heartbeatMs={} deadband[target={} sim={} sensor={} error={} iError={} ctrlOut={} pwmDuty={} pwmNorm={} param={}]",
        version,
        rule.scopeType(),
        rule.scopeValue(),
        rule.rawMode(),
        rule.enabled(),
        rule.summaryEnabled(),
        rule.summaryMinSamples(),
        rule.heartbeatIntervalMs(),
        rule.targetTempDeadband(),
        rule.simTempDeadband(),
        rule.sensorTempDeadband(),
        rule.errorDeadband(),
        rule.integralErrorDeadband(),
        rule.controlOutputDeadband(),
        rule.pwmDutyDeadband(),
        rule.pwmNormDeadband(),
        rule.parameterDeadband()));
  }

  private StorageRuleDefinition applyRawModeDefaults(StorageRuleDefinition source) {
    String mode = normalizeRawMode(source.rawMode());
    double factor = 1.0d;
    if ("strict".equals(mode)) {
      factor = 0.5d;
    } else if ("relaxed".equals(mode)) {
      factor = 2.0d;
    }

    return new StorageRuleDefinition(
        source.id(),
        source.scopeType(),
        source.scopeValue(),
        mode,
        source.summaryEnabled(),
        source.summaryMinSamples(),
        source.heartbeatIntervalMs(),
        source.targetTempDeadband() * factor,
        source.simTempDeadband() * factor,
        source.sensorTempDeadband() * factor,
        source.errorDeadband() * factor,
        source.integralErrorDeadband() * factor,
        source.controlOutputDeadband() * factor,
        Math.max(0, (int) Math.round(source.pwmDutyDeadband() * factor)),
        source.pwmNormDeadband() * factor,
        source.parameterDeadband() * factor,
        source.enabled());
  }

  private Map<String, AlarmRuleDefinition> defaultAlarmRules() {
    Map<String, AlarmRuleDefinition> defaults = new LinkedHashMap<>();
    defaults.put("out_of_band", new AlarmRuleDefinition("out_of_band", "Out of Band", "temperature_error", ">", "0.5", 30, "warning", true, "global", "*"));
    defaults.put("sensor_invalid", new AlarmRuleDefinition("sensor_invalid", "Sensor Invalid", "sensor_valid", "==", "false", 10, "critical", true, "global", "*"));
    defaults.put("high_saturation", new AlarmRuleDefinition("high_saturation", "High Saturation", "pwm_output", ">=", "85", 60, "warning", true, "global", "*"));
    defaults.put("fault_latched", new AlarmRuleDefinition("fault_latched", "Fault Latched", "fault_latched", "==", "true", 0, "critical", true, "global", "*"));
    defaults.put("safety_output_forced_off", new AlarmRuleDefinition("safety_output_forced_off", "Safety Output Forced Off", "safety_output_forced_off", "==", "true", 0, "critical", true, "global", "*"));
    defaults.put("max_safe_temp_exceeded", new AlarmRuleDefinition("max_safe_temp_exceeded", "Software Max Safe Temp Exceeded", "sensor_temp_c", ">", "dynamic_from_payload", 0, "critical", true, "global", "*"));
    defaults.put("control_dt_deviation", new AlarmRuleDefinition("control_dt_deviation", "Control Dt Deviation", "dt_error_ms", ">=", "200", 20, "warning", true, "global", "*"));
    defaults.put("param_apply_failed", new AlarmRuleDefinition("param_apply_failed", "Param Apply Failed", "params_ack", "==", "failed", 5, "warning", true, "global", "*"));
    defaults.put("device_offline", new AlarmRuleDefinition("device_offline", "Device Offline", "telemetry_gap", ">", "60", 60, "critical", true, "global", "*"));
    return defaults;
  }

  private StorageRuleDefinition defaultStorageRule() {
    HubProperties.TelemetryFilter filter = properties.getTelemetryFilter();
    HubProperties.TelemetrySummary summary = properties.getTelemetrySummary();
    return new StorageRuleDefinition(
        0L,
        "global",
        "*",
        "full",
        summary.isEnabled(),
        Math.max(1, summary.getMinSamples()),
        Math.max(0L, filter.getHeartbeatIntervalMs()),
        Math.max(0d, filter.getTargetTempDeadband()),
        Math.max(0d, filter.getSimTempDeadband()),
        Math.max(0d, filter.getSensorTempDeadband()),
        Math.max(0d, filter.getErrorDeadband()),
        Math.max(0d, filter.getIntegralErrorDeadband()),
        Math.max(0d, filter.getControlOutputDeadband()),
        Math.max(0, filter.getPwmDutyDeadband()),
        Math.max(0d, filter.getPwmNormDeadband()),
        Math.max(0d, filter.getParameterDeadband()),
        filter.isEnabled());
  }
}
