package com.edgehub.datahub.model;

public record ParameterAckPayload(
    String device_id,
    String ack_type,
    boolean success,
    boolean applied_immediately,
    boolean has_pending_params,
    double target_temp_c,
    double kp,
    double ki,
    double kd,
    long control_period_ms,
    String control_mode,
    String reason,
    long uptime_ms,
    Boolean sensor_valid,
    Boolean fault_latched,
    String fault_reason,
    Double software_max_safe_temp_c) {}
