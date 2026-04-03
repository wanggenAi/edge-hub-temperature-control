package com.edgehub.datahub.pipeline;

import com.edgehub.datahub.config.HubProperties;
import com.edgehub.datahub.model.DeviceStatusSnapshot;
import com.edgehub.datahub.model.ParsedHubMessage;
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import com.github.benmanes.caffeine.cache.RemovalCause;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import org.springframework.stereotype.Component;

import com.edgehub.datahub.monitoring.DataHubMetrics;

@Component
public final class DeviceStatusTracker {

  private final HubProperties.DeviceStatus properties;
  private final DataHubMetrics metrics;
  private final Cache<String, DevicePresence> devices;

  public DeviceStatusTracker(HubProperties hubProperties, DataHubMetrics metrics) {
    this.properties = hubProperties.getDeviceStatus();
    this.metrics = metrics;
    this.devices = Caffeine.newBuilder()
        .maximumSize(Math.max(1L, properties.getMaxActiveDevices()))
        .expireAfterAccess(Duration.ofMillis(Math.max(1000L, properties.getStateTtlMs())))
        .removalListener((String deviceId, DevicePresence ignored, RemovalCause cause) -> {
          if (deviceId == null || cause == RemovalCause.EXPLICIT || cause == RemovalCause.REPLACED) {
            return;
          }
          metrics.recordDeviceStatusStateEvicted();
        })
        .build();
    metrics.updateDeviceStatusStateSize(0L);
  }

  public StatusBatch onMessage(ParsedHubMessage message) {
    if (!properties.isEnabled()) {
      return new StatusBatch(List.of());
    }
    devices.cleanUp();
    StatusHolder holder = new StatusHolder();

    if (message instanceof ParsedHubMessage.TelemetryMessage telemetry) {
      String deviceId = telemetry.topic().deviceId();
      if (deviceId == null || deviceId.isBlank()) {
        return new StatusBatch(List.of());
      }
      devices.asMap().compute(deviceId, (ignored, existing) -> {
        DevicePresence next = existing == null
            ? DevicePresence.firstSeen(telemetry.receivedAt(), telemetry.topic().rawTopic(), telemetry.payload().system_state(), "telemetry")
            : existing.touch(telemetry.receivedAt(), telemetry.topic().rawTopic(), telemetry.payload().system_state(), "telemetry");
        holder.status = next.transitionStatus(deviceId, telemetry.receivedAt());
        return next;
      });
      metrics.updateDeviceStatusStateSize(devices.estimatedSize());
      return new StatusBatch(holder.status == null ? List.of() : List.of(holder.status));
    }

    if (message instanceof ParsedHubMessage.ParameterAckMessage parameterAck) {
      String deviceId = parameterAck.topic().deviceId();
      if (deviceId == null || deviceId.isBlank()) {
        return new StatusBatch(List.of());
      }
      devices.asMap().compute(deviceId, (ignored, existing) -> {
        DevicePresence next = existing == null
            ? DevicePresence.firstSeen(parameterAck.receivedAt(), parameterAck.topic().rawTopic(), null, "params_ack")
            : existing.touch(parameterAck.receivedAt(), parameterAck.topic().rawTopic(), existing == null ? null : existing.systemState(), "params_ack");
        holder.status = next.transitionStatus(deviceId, parameterAck.receivedAt());
        return next;
      });
      metrics.updateDeviceStatusStateSize(devices.estimatedSize());
      return new StatusBatch(holder.status == null ? List.of() : List.of(holder.status));
    }

    return new StatusBatch(List.of());
  }

  public List<DeviceStatusSnapshot> flushOffline(Instant now) {
    if (!properties.isEnabled()) {
      return List.of();
    }
    devices.cleanUp();
    List<DeviceStatusSnapshot> updates = new ArrayList<>();
    long onlineTimeoutMs = Math.max(1000L, properties.getOnlineTimeoutMs());
    devices.asMap().forEach((deviceId, existing) -> {
      if (existing == null || !existing.online()) {
        return;
      }
      long silentMs = now.toEpochMilli() - existing.lastSeenAt().toEpochMilli();
      if (silentMs < onlineTimeoutMs) {
        return;
      }
      DevicePresence next = existing.markOffline();
      if (!devices.asMap().replace(deviceId, existing, next)) {
        return;
      }
      updates.add(next.transitionStatus(deviceId, now));
    });
    metrics.updateDeviceStatusStateSize(devices.estimatedSize());
    return updates;
  }

  public record StatusBatch(List<DeviceStatusSnapshot> updates) {}

  private record DevicePresence(
      Instant lastSeenAt,
      String rawTopic,
      String systemState,
      String lastMessageKind,
      boolean online,
      String transitionReason) {

    private static DevicePresence firstSeen(Instant observedAt, String rawTopic, String systemState, String lastMessageKind) {
      return new DevicePresence(
          observedAt,
          rawTopic,
          normalizeSystemState(systemState),
          lastMessageKind,
          true,
          "first_seen");
    }

    private DevicePresence touch(Instant observedAt, String rawTopic, String systemState, String lastMessageKind) {
      String nextSystemState = normalizeSystemState(systemState != null ? systemState : this.systemState);
      boolean regained = !online;
      boolean stateChanged = !Objects.equals(this.systemState, nextSystemState);
      String nextReason;
      if (regained) {
        nextReason = "reconnected";
      } else if (stateChanged && nextSystemState != null) {
        nextReason = "system_state_changed";
      } else {
        nextReason = null;
      }
      return new DevicePresence(observedAt, rawTopic, nextSystemState, lastMessageKind, true, nextReason);
    }

    private DevicePresence markOffline() {
      return new DevicePresence(lastSeenAt, rawTopic, systemState, lastMessageKind, false, "telemetry_timeout");
    }

    private DeviceStatusSnapshot transitionStatus(String deviceId, Instant observedAt) {
      if (transitionReason == null) {
        return null;
      }
      return new DeviceStatusSnapshot(
          deviceId,
          rawTopic,
          observedAt,
          lastSeenAt,
          online,
          transitionReason,
          systemState,
          lastMessageKind);
    }

    private static String normalizeSystemState(String value) {
      if (value == null || value.isBlank()) {
        return "unknown";
      }
      return value;
    }
  }

  private static final class StatusHolder {
    private DeviceStatusSnapshot status;
  }
}
