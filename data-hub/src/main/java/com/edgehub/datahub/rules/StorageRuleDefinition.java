package com.edgehub.datahub.rules;

public record StorageRuleDefinition(
    Long id,
    String scopeType,
    String scopeValue,
    String rawMode,
    boolean summaryEnabled,
    int summaryMinSamples,
    long heartbeatIntervalMs,
    double targetTempDeadband,
    double simTempDeadband,
    double sensorTempDeadband,
    double errorDeadband,
    double integralErrorDeadband,
    double controlOutputDeadband,
    int pwmDutyDeadband,
    double pwmNormDeadband,
    double parameterDeadband,
    boolean enabled) {}
