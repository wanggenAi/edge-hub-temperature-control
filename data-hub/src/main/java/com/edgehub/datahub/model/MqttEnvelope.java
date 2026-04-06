package com.edgehub.datahub.model;

import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Runtime MQTT envelope used by the reactive consume pipeline.
 * Ack is intentionally manual so persistence success can control commit timing.
 */
public final class MqttEnvelope {

  private final String topic;
  private final String payload;
  private final int qos;
  private final boolean retain;
  private final Long messageId;
  private final String deviceId;
  private final Instant receiveTime;
  private final Runnable ackHandle;
  private final AtomicBoolean acked = new AtomicBoolean();

  public MqttEnvelope(
      String topic,
      String payload,
      int qos,
      boolean retain,
      Long messageId,
      String deviceId,
      Instant receiveTime,
      Runnable ackHandle) {
    this.topic = Objects.requireNonNull(topic, "topic");
    this.payload = Objects.requireNonNull(payload, "payload");
    this.qos = qos;
    this.retain = retain;
    this.messageId = messageId;
    this.deviceId = Objects.requireNonNullElse(deviceId, "unknown");
    this.receiveTime = Objects.requireNonNull(receiveTime, "receiveTime");
    this.ackHandle = Objects.requireNonNullElse(ackHandle, () -> {});
  }

  public String topic() {
    return topic;
  }

  public String payload() {
    return payload;
  }

  public int qos() {
    return qos;
  }

  public boolean retain() {
    return retain;
  }

  public Long messageId() {
    return messageId;
  }

  public String deviceId() {
    return deviceId;
  }

  public Instant receiveTime() {
    return receiveTime;
  }

  public boolean acked() {
    return acked.get();
  }

  public void ack() {
    if (acked.compareAndSet(false, true)) {
      ackHandle.run();
    }
  }

  public RawMqttMessage asRawMessage() {
    return new RawMqttMessage(topic, payload, receiveTime);
  }
}

