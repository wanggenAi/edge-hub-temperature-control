package com.edgehub.datahub.model;

import java.time.Instant;

public record DeviceStatusSnapshot(
    String deviceId,
    String rawTopic,
    Instant observedAt,
    Instant lastSeenAt,
    boolean online,
    String statusReason,
    String systemState,
    String lastMessageKind) {}
