package com.edgehub.datahub.pipeline;

import com.edgehub.datahub.config.HubProperties;
import com.edgehub.datahub.model.ParsedHubMessage;
import com.edgehub.datahub.model.TelemetryPayload;
import com.edgehub.datahub.model.TelemetrySteadySummary;
import java.time.Instant;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public final class TelemetrySummaryAggregator {

  private final HubProperties.TelemetrySummary properties;
  private final ConcurrentHashMap<String, SummaryWindow> pendingWindowsByDevice = new ConcurrentHashMap<>();

  public TelemetrySummaryAggregator(HubProperties hubProperties) {
    this.properties = hubProperties.getTelemetrySummary();
  }

  public Optional<TelemetrySteadySummary> onTelemetry(
      ParsedHubMessage.TelemetryMessage telemetry,
      TelemetryWriteFilter.FilterDecision decision) {
    if (!properties.isEnabled()) {
      return Optional.empty();
    }

    String deviceId = telemetry.topic().deviceId();
    if (deviceId == null || deviceId.isBlank()) {
      return Optional.empty();
    }

    if (decision.persist()) {
      return flush(deviceId, decision.reason());
    }

    pendingWindowsByDevice.compute(
        deviceId,
        (ignored, existing) -> existing == null ? SummaryWindow.from(telemetry) : existing.append(telemetry));
    return Optional.empty();
  }

  public Optional<TelemetrySteadySummary> flush(String deviceId, String flushReason) {
    if (!properties.isEnabled() || deviceId == null || deviceId.isBlank()) {
      return Optional.empty();
    }

    SummaryWindow window = pendingWindowsByDevice.remove(deviceId);
    int minSamples = Math.max(properties.getMinSamples(), 1);
    if (window == null || window.sampleCount() < minSamples) {
      return Optional.empty();
    }
    return Optional.of(window.toSummary(flushReason));
  }

  private static long normalizeControlPeriodMs(Long value) {
    return value == null ? 0L : value.longValue();
  }

  private record SummaryWindow(
      String deviceId,
      String rawTopic,
      String runId,
      Instant windowStart,
      Instant windowEnd,
      int sampleCount,
      long controlPeriodMs,
      long uptimeStartMs,
      long uptimeEndMs,
      double targetTempSum,
      double simTempSum,
      double sensorTempSum,
      int sensorTempCount,
      Double sensorTempMin,
      Double sensorTempMax,
      double errorSum,
      double absErrorSum,
      double absErrorMax,
      double controlOutputSum,
      double controlOutputMin,
      double controlOutputMax,
      long pwmDutySum,
      int pwmDutyMin,
      int pwmDutyMax,
      double pwmNormSum,
      double pwmNormMin,
      double pwmNormMax,
      String controlMode,
      String systemState,
      double kp,
      double ki,
      double kd) {

    private static SummaryWindow from(ParsedHubMessage.TelemetryMessage telemetry) {
      TelemetryPayload payload = telemetry.payload();
      Double sensorTemp = payload.sensor_temp_c();
      return new SummaryWindow(
          telemetry.topic().deviceId(),
          telemetry.topic().rawTopic(),
          payload.run_id(),
          telemetry.receivedAt(),
          telemetry.receivedAt(),
          1,
          normalizeControlPeriodMs(payload.control_period_ms()),
          payload.uptime_ms(),
          payload.uptime_ms(),
          payload.target_temp_c(),
          payload.sim_temp_c(),
          sensorTemp == null ? 0.0 : sensorTemp,
          sensorTemp == null ? 0 : 1,
          sensorTemp,
          sensorTemp,
          payload.error_c(),
          Math.abs(payload.error_c()),
          Math.abs(payload.error_c()),
          payload.control_output(),
          payload.control_output(),
          payload.control_output(),
          payload.pwm_duty(),
          payload.pwm_duty(),
          payload.pwm_duty(),
          payload.pwm_norm(),
          payload.pwm_norm(),
          payload.pwm_norm(),
          payload.control_mode(),
          payload.system_state(),
          payload.kp(),
          payload.ki(),
          payload.kd());
    }

    private SummaryWindow append(ParsedHubMessage.TelemetryMessage telemetry) {
      TelemetryPayload payload = telemetry.payload();
      Double sensorTemp = payload.sensor_temp_c();
      double nextSensorSum = sensorTempSum + (sensorTemp == null ? 0.0 : sensorTemp);
      int nextSensorCount = sensorTempCount + (sensorTemp == null ? 0 : 1);
      Double nextSensorMin = sensorTemp == null ? sensorTempMin : sensorTempMin == null ? sensorTemp : Math.min(sensorTempMin, sensorTemp);
      Double nextSensorMax = sensorTemp == null ? sensorTempMax : sensorTempMax == null ? sensorTemp : Math.max(sensorTempMax, sensorTemp);
      double absError = Math.abs(payload.error_c());
      return new SummaryWindow(
          deviceId,
          telemetry.topic().rawTopic(),
          payload.run_id(),
          windowStart,
          telemetry.receivedAt(),
          sampleCount + 1,
          normalizeControlPeriodMs(payload.control_period_ms()),
          uptimeStartMs,
          payload.uptime_ms(),
          targetTempSum + payload.target_temp_c(),
          simTempSum + payload.sim_temp_c(),
          nextSensorSum,
          nextSensorCount,
          nextSensorMin,
          nextSensorMax,
          errorSum + payload.error_c(),
          absErrorSum + absError,
          Math.max(absErrorMax, absError),
          controlOutputSum + payload.control_output(),
          Math.min(controlOutputMin, payload.control_output()),
          Math.max(controlOutputMax, payload.control_output()),
          pwmDutySum + payload.pwm_duty(),
          Math.min(pwmDutyMin, payload.pwm_duty()),
          Math.max(pwmDutyMax, payload.pwm_duty()),
          pwmNormSum + payload.pwm_norm(),
          Math.min(pwmNormMin, payload.pwm_norm()),
          Math.max(pwmNormMax, payload.pwm_norm()),
          payload.control_mode(),
          payload.system_state(),
          payload.kp(),
          payload.ki(),
          payload.kd());
    }

    private TelemetrySteadySummary toSummary(String flushReason) {
      return new TelemetrySteadySummary(
          deviceId,
          rawTopic,
          runId,
          windowStart,
          windowEnd,
          windowEnd.toEpochMilli() - windowStart.toEpochMilli(),
          flushReason,
          sampleCount,
          controlPeriodMs,
          uptimeStartMs,
          uptimeEndMs,
          targetTempSum / sampleCount,
          simTempSum / sampleCount,
          sensorTempCount == 0 ? null : sensorTempSum / sensorTempCount,
          sensorTempMin,
          sensorTempMax,
          errorSum / sampleCount,
          absErrorSum / sampleCount,
          absErrorMax,
          controlOutputSum / sampleCount,
          controlOutputMin,
          controlOutputMax,
          (double) pwmDutySum / sampleCount,
          pwmDutyMin,
          pwmDutyMax,
          pwmNormSum / sampleCount,
          pwmNormMin,
          pwmNormMax,
          controlMode,
          systemState,
          kp,
          ki,
          kd);
    }
  }
}
