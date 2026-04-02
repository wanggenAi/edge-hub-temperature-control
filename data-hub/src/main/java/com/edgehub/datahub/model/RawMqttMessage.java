package com.edgehub.datahub.model;

import java.time.Instant;

public record RawMqttMessage(String topic, String payload, Instant receivedAt) {}
