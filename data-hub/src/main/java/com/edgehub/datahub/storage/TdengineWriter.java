package com.edgehub.datahub.storage;

import com.edgehub.datahub.model.ParsedHubMessage;
import reactor.core.publisher.Mono;

public interface TdengineWriter {

  Mono<Void> writeTelemetry(ParsedHubMessage.TelemetryMessage telemetry);

  Mono<Void> writeParameterSet(ParsedHubMessage.ParameterSetMessage parameterSet);

  Mono<Void> writeParameterAck(ParsedHubMessage.ParameterAckMessage parameterAck);
}
