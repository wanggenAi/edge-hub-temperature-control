package com.edgehub.datahub.model;

import java.util.Optional;

public record DeviceTopic(String rawTopic, String deviceId, TopicKind kind) {

  public static Optional<DeviceTopic> parseFlexible(String topic) {
    String[] parts = topic.split("/");
    if (parts.length == 4) {
      if (!"edge".equals(parts[0]) || !"temperature".equals(parts[1])) {
        return Optional.empty();
      }
      if (!"telemetry".equals(parts[3])) {
        return Optional.empty();
      }
      return Optional.of(new DeviceTopic(topic, parts[2], TopicKind.TELEMETRY));
    }
    if (parts.length != 5) {
      return Optional.empty();
    }
    if (!"edge".equals(parts[0]) || !"temperature".equals(parts[1])) {
      return Optional.empty();
    }
    if (!"params".equals(parts[3])) {
      return Optional.empty();
    }
    return switch (parts[4]) {
      case "set" -> Optional.of(new DeviceTopic(topic, parts[2], TopicKind.PARAMS_SET));
      case "ack" -> Optional.of(new DeviceTopic(topic, parts[2], TopicKind.PARAMS_ACK));
      default -> Optional.empty();
    };
  }
}
