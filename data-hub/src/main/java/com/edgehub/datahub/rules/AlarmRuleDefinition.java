package com.edgehub.datahub.rules;

public record AlarmRuleDefinition(
    String ruleCode,
    String name,
    String target,
    String operator,
    String threshold,
    Integer holdSeconds,
    String severity,
    Boolean enabled,
    String scopeType,
    String scopeValue) {}
