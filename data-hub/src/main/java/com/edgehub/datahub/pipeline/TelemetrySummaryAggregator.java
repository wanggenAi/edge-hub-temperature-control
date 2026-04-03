package com.edgehub.datahub.pipeline;

import com.edgehub.datahub.config.HubProperties;
import com.edgehub.datahub.model.ParsedHubMessage;
import com.edgehub.datahub.model.TelemetryPayload;
import com.edgehub.datahub.model.TelemetrySteadySummary;
import com.edgehub.datahub.monitoring.DataHubMetrics;
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.RemovalCause;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentLinkedQueue;
import org.springframework.stereotype.Component;

@Component
public final class TelemetrySummaryAggregator {

  private final HubProperties.TelemetrySummary properties;
  private final DataHubMetrics metrics;
  private final Cache<String, SummaryWindow> pendingWindowsByDevice;
  private final ConcurrentLinkedQueue<TelemetrySteadySummary> evictedSummaries = new ConcurrentLinkedQueue<>();

  public TelemetrySummaryAggregator(HubProperties hubProperties, DataHubMetrics metrics) {
    this.properties = hubProperties.getTelemetrySummary();
    this.metrics = metrics;
    this.pendingWindowsByDevice = Caffeine.newBuilder()
        .maximumSize(Math.max(1L, properties.getMaxActiveWindows()))
        .expireAfterAccess(Duration.ofMillis(Math.max(1000L, properties.getWindowTtlMs())))
        .removalListener((String deviceId, SummaryWindow window, RemovalCause cause) -> {
          if (deviceId == null || window == null) {
            return;
          }
          if (cause == RemovalCause.EXPLICIT || cause == RemovalCause.REPLACED) {
            return;
          }
          metrics.recordTelemetrySummaryWindowEvicted();
          if (window.sampleCount() < Math.max(properties.getMinSamples(), 1)) {
            metrics.recordTelemetrySummaryWindowDiscarded();
            return;
          }
          evictedSummaries.add(window.toSummary(cause == RemovalCause.SIZE ? "cache_size_limit" : "cache_expired"));
        })
        .build();
    metrics.updateTelemetrySummaryWindowSize(0L);
  }

  public SummaryBatch onTelemetry(
      ParsedHubMessage.TelemetryMessage telemetry,
      TelemetryWriteFilter.FilterDecision decision) {
    List<TelemetrySteadySummary> summaries = drainEvictedSummaries();
    if (!properties.isEnabled()) {
      return new SummaryBatch(summaries);
    }

    String deviceId = telemetry.topic().deviceId();
    if (deviceId == null || deviceId.isBlank()) {
      return new SummaryBatch(summaries);
    }

    pendingWindowsByDevice.cleanUp();

    if (decision.persist()) {
      flushCurrentWindow(deviceId, decision.reason()).ifPresent(summaries::add);
      metrics.updateTelemetrySummaryWindowSize(pendingWindowsByDevice.estimatedSize());
      return new SummaryBatch(summaries);
    }

    pendingWindowsByDevice.asMap().compute(
        deviceId,
        (ignored, existing) -> existing == null ? SummaryWindow.from(telemetry) : existing.append(telemetry));
    metrics.updateTelemetrySummaryWindowSize(pendingWindowsByDevice.estimatedSize());
    return new SummaryBatch(summaries);
  }

  public SummaryBatch flush(String deviceId, String flushReason) {
    List<TelemetrySteadySummary> summaries = drainEvictedSummaries();
    if (!properties.isEnabled() || deviceId == null || deviceId.isBlank()) {
      return new SummaryBatch(summaries);
    }
    pendingWindowsByDevice.cleanUp();
    flushCurrentWindow(deviceId, flushReason).ifPresent(summaries::add);
    metrics.updateTelemetrySummaryWindowSize(pendingWindowsByDevice.estimatedSize());
    return new SummaryBatch(summaries);
  }

  public List<TelemetrySteadySummary> flushIdle(Instant now) {
    List<TelemetrySteadySummary> summaries = drainEvictedSummaries();
    if (!properties.isEnabled() || properties.getIdleFlushIntervalMs() <= 0) {
      return summaries;
    }

    pendingWindowsByDevice.cleanUp();
    long idleFlushIntervalMs = properties.getIdleFlushIntervalMs();
    int minSamples = Math.max(properties.getMinSamples(), 1);
    pendingWindowsByDevice.asMap().forEach((deviceId, window) -> {
      if (window == null) {
        return;
      }
      long idleMs = now.toEpochMilli() - window.windowEnd().toEpochMilli();
      if (idleMs < idleFlushIntervalMs) {
        return;
      }
      if (!pendingWindowsByDevice.asMap().remove(deviceId, window)) {
        return;
      }
      if (window.sampleCount() < minSamples) {
        metrics.recordTelemetrySummaryWindowDiscarded();
        return;
      }
      summaries.add(window.toSummary("idle_timeout"));
    });
    metrics.updateTelemetrySummaryWindowSize(pendingWindowsByDevice.estimatedSize());
    return summaries;
  }

  public List<TelemetrySteadySummary> flushAll(String flushReason) {
    List<TelemetrySteadySummary> summaries = drainEvictedSummaries();
    if (!properties.isEnabled()) {
      return summaries;
    }

    int minSamples = Math.max(properties.getMinSamples(), 1);
    pendingWindowsByDevice.asMap().forEach((deviceId, window) -> {
      if (window == null || !pendingWindowsByDevice.asMap().remove(deviceId, window)) {
        return;
      }
      if (window.sampleCount() < minSamples) {
        metrics.recordTelemetrySummaryWindowDiscarded();
        return;
      }
      summaries.add(window.toSummary(flushReason));
    });
    metrics.updateTelemetrySummaryWindowSize(pendingWindowsByDevice.estimatedSize());
    return summaries;
  }

  private Optional<TelemetrySteadySummary> flushCurrentWindow(String deviceId, String flushReason) {
    SummaryWindow window = pendingWindowsByDevice.asMap().remove(deviceId);
    int minSamples = Math.max(properties.getMinSamples(), 1);
    if (window == null || window.sampleCount() < minSamples) {
      if (window != null) {
        metrics.recordTelemetrySummaryWindowDiscarded();
      }
      return Optional.empty();
    }
    return Optional.of(window.toSummary(flushReason));
  }

  private List<TelemetrySteadySummary> drainEvictedSummaries() {
    pendingWindowsByDevice.cleanUp();
    List<TelemetrySteadySummary> drained = new ArrayList<>();
    TelemetrySteadySummary summary;
    while ((summary = evictedSummaries.poll()) != null) {
      drained.add(summary);
    }
    metrics.updateTelemetrySummaryWindowSize(pendingWindowsByDevice.estimatedSize());
    return drained;
  }

  public record SummaryBatch(List<TelemetrySteadySummary> summaries) {}

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
