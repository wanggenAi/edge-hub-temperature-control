package com.edgehub.datahub.storage;

import com.edgehub.datahub.model.ParsedHubMessage;
import com.edgehub.datahub.model.TelemetrySteadySummary;
import reactor.core.publisher.Mono;

public interface TdengineWriter {

  Mono<Void> writeTelemetry(ParsedHubMessage.TelemetryMessage telemetry);

  Mono<Void> writeTelemetrySummary(TelemetrySteadySummary summary);

  Mono<Void> writeParameterSet(ParsedHubMessage.ParameterSetMessage parameterSet);

  Mono<Void> writeParameterAck(ParsedHubMessage.ParameterAckMessage parameterAck);
}
