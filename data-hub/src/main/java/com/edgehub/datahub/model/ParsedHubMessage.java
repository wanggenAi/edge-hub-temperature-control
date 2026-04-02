package com.edgehub.datahub.model;

import java.time.Instant;

public sealed interface ParsedHubMessage permits ParsedHubMessage.TelemetryMessage, ParsedHubMessage.ParameterSetMessage, ParsedHubMessage.ParameterAckMessage {

  DeviceTopic topic();

  Instant receivedAt();

  record TelemetryMessage(DeviceTopic topic, Instant receivedAt, TelemetryPayload payload) implements ParsedHubMessage {}

  record ParameterSetMessage(DeviceTopic topic, Instant receivedAt, ParameterSetPayload payload) implements ParsedHubMessage {}

  record ParameterAckMessage(DeviceTopic topic, Instant receivedAt, ParameterAckPayload payload) implements ParsedHubMessage {}
}
