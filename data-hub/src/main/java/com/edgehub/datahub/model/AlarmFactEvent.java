package com.edgehub.datahub.model;

import java.time.Instant;

public record AlarmFactEvent(
    String deviceId,
    String ruleCode,
    String severity,
    String source,
    String reason,
    String eventType,
    Instant eventTime,
    Instant triggeredAt,
    Long durationSeconds,
    String contextJson) {}
