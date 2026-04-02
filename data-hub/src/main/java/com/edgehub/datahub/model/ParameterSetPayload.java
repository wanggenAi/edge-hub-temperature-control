package com.edgehub.datahub.model;

public record ParameterSetPayload(
    Double target_temp_c,
    Double kp,
    Double ki,
    Double kd,
    Long control_period_ms,
    String control_mode,
    Boolean apply_immediately) {}
