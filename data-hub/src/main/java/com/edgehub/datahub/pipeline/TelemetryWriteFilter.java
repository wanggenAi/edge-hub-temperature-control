package com.edgehub.datahub.pipeline;

import com.edgehub.datahub.config.HubProperties;
import com.edgehub.datahub.model.ParsedHubMessage;
import com.edgehub.datahub.model.TelemetryPayload;
import com.edgehub.datahub.monitoring.DataHubMetrics;
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.RemovalCause;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public final class TelemetryWriteFilter {

  private static final Logger log = LoggerFactory.getLogger(TelemetryWriteFilter.class);

  private final HubProperties.TelemetryFilter properties;
  private final DataHubMetrics metrics;
  private final Cache<String, DeviceState> lastPersistedByDevice;

  public TelemetryWriteFilter(HubProperties hubProperties, DataHubMetrics metrics) {
    this.properties = hubProperties.getTelemetryFilter();
    this.metrics = metrics;
    this.lastPersistedByDevice = Caffeine.newBuilder()
        .maximumSize(Math.max(1L, properties.getMaxActiveDevices()))
        .expireAfterAccess(Duration.ofMillis(Math.max(1000L, properties.getStateTtlMs())))
        .removalListener((String deviceId, DeviceState ignored, RemovalCause cause) -> {
          if (deviceId == null || cause == RemovalCause.EXPLICIT || cause == RemovalCause.REPLACED) {
            return;
          }
          metrics.recordTelemetryFilterStateEvicted();
        })
        .build();
    metrics.updateTelemetryFilterStateSize(0L);
  }

  public FilterDecision evaluate(ParsedHubMessage.TelemetryMessage telemetry) {
    if (!properties.isEnabled()) {
      return FilterDecision.persist("filter_disabled");
    }

    String deviceId = telemetry.topic().deviceId();
    if (deviceId == null || deviceId.isBlank()) {
      return FilterDecision.persist("missing_device_id");
    }

    lastPersistedByDevice.cleanUp();
    DecisionHolder holder = new DecisionHolder();
    lastPersistedByDevice.asMap().compute(deviceId, (ignored, existing) -> {
      if (existing == null) {
        holder.decision = FilterDecision.persist("first_sample");
        return DeviceState.from(telemetry);
      }

      if (heartbeatDue(existing.persistedAt(), telemetry.receivedAt())) {
        holder.decision = FilterDecision.persist("heartbeat");
        return DeviceState.from(telemetry);
      }

      String changeReason = detectMeaningfulChange(existing.payload(), telemetry.payload());
      if (changeReason != null) {
        holder.decision = FilterDecision.persist(changeReason);
        return DeviceState.from(telemetry);
      }

      holder.decision = FilterDecision.skip("steady_state_duplicate");
      return existing;
    });
    metrics.updateTelemetryFilterStateSize(lastPersistedByDevice.estimatedSize());

    if (!holder.decision.persist()) {
      metrics.recordTelemetrySkipped();
      if (properties.isLogSkips()) {
        TelemetryPayload payload = telemetry.payload();
        log.info(
            "telemetry skipped device={} reason={} uptimeMs={} targetTemp={} simTemp={} sensorTemp={} error={} pwmDuty={}",
            telemetry.topic().deviceId(),
            holder.decision.reason(),
            payload.uptime_ms(),
            payload.target_temp_c(),
            payload.sim_temp_c(),
            payload.sensor_temp_c(),
            payload.error_c(),
            payload.pwm_duty());
      }
    }

    return holder.decision;
  }

  public void invalidate(String deviceId, String reason) {
    if (!properties.isEnabled() || deviceId == null || deviceId.isBlank()) {
      return;
    }
    lastPersistedByDevice.invalidate(deviceId);
    metrics.updateTelemetryFilterStateSize(lastPersistedByDevice.estimatedSize());
    if (properties.isLogSkips()) {
      log.info("telemetry filter state reset device={} reason={}", deviceId, reason);
    }
  }

  private boolean heartbeatDue(Instant lastPersistedAt, Instant receivedAt) {
    long heartbeatIntervalMs = properties.getHeartbeatIntervalMs();
    if (heartbeatIntervalMs <= 0) {
      return false;
    }
    return receivedAt.toEpochMilli() - lastPersistedAt.toEpochMilli() >= heartbeatIntervalMs;
  }

  private String detectMeaningfulChange(TelemetryPayload previous, TelemetryPayload current) {
    if (!Objects.equals(previous.run_id(), current.run_id())) {
      return "run_id_changed";
    }
    if (!Objects.equals(previous.control_period_ms(), current.control_period_ms())) {
      return "control_period_changed";
    }
    if (!Objects.equals(previous.saturation_state(), current.saturation_state())) {
      return "saturation_state_changed";
    }
    if (!Objects.equals(previous.sensor_valid(), current.sensor_valid())) {
      return "sensor_valid_changed";
    }
    if (!Objects.equals(previous.control_mode(), current.control_mode())) {
      return "control_mode_changed";
    }
    if (!Objects.equals(previous.controller_version(), current.controller_version())) {
      return "controller_version_changed";
    }
    if (!Objects.equals(previous.system_state(), current.system_state())) {
      return "system_state_changed";
    }
    if (previous.has_pending_params() != current.has_pending_params()) {
      return "pending_params_flag_changed";
    }
    if (changed(previous.target_temp_c(), current.target_temp_c(), properties.getTargetTempDeadband())) {
      return "target_temp_changed";
    }
    if (changed(previous.sim_temp_c(), current.sim_temp_c(), properties.getSimTempDeadband())) {
      return "sim_temp_changed";
    }
    if (changedNullable(previous.sensor_temp_c(), current.sensor_temp_c(), properties.getSensorTempDeadband())) {
      return "sensor_temp_changed";
    }
    if (changed(previous.error_c(), current.error_c(), properties.getErrorDeadband())) {
      return "error_changed";
    }
    if (changed(previous.integral_error(), current.integral_error(), properties.getIntegralErrorDeadband())) {
      return "integral_error_changed";
    }
    if (changed(previous.control_output(), current.control_output(), properties.getControlOutputDeadband())) {
      return "control_output_changed";
    }
    if (changed(previous.pwm_duty(), current.pwm_duty(), properties.getPwmDutyDeadband())) {
      return "pwm_duty_changed";
    }
    if (changed(previous.pwm_norm(), current.pwm_norm(), properties.getPwmNormDeadband())) {
      return "pwm_norm_changed";
    }
    if (changed(previous.kp(), current.kp(), properties.getParameterDeadband())) {
      return "kp_changed";
    }
    if (changed(previous.ki(), current.ki(), properties.getParameterDeadband())) {
      return "ki_changed";
    }
    if (changed(previous.kd(), current.kd(), properties.getParameterDeadband())) {
      return "kd_changed";
    }
    return null;
  }

  private boolean changed(double previous, double current, double deadband) {
    if (deadband <= 0) {
      return Double.compare(previous, current) != 0;
    }
    return Math.abs(previous - current) > deadband;
  }

  private boolean changed(int previous, int current, int deadband) {
    if (deadband <= 0) {
      return previous != current;
    }
    return Math.abs(previous - current) > deadband;
  }

  private boolean changedNullable(Double previous, Double current, double deadband) {
    if (previous == null && current == null) {
      return false;
    }
    if (previous == null || current == null) {
      return true;
    }
    return changed(previous.doubleValue(), current.doubleValue(), deadband);
  }

  public record FilterDecision(boolean persist, String reason) {

    public static FilterDecision persist(String reason) {
      return new FilterDecision(true, reason);
    }

    public static FilterDecision skip(String reason) {
      return new FilterDecision(false, reason);
    }
  }

  private record DeviceState(Instant persistedAt, TelemetryPayload payload) {

    private static DeviceState from(ParsedHubMessage.TelemetryMessage telemetry) {
      return new DeviceState(telemetry.receivedAt(), telemetry.payload());
    }
  }

  private static final class DecisionHolder {
    private FilterDecision decision = FilterDecision.persist("first_sample");
  }
}
