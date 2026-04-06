package com.edgehub.datahub.storage;

import com.edgehub.datahub.model.MqttEnvelope;
import com.edgehub.datahub.model.ParsedHubMessage;
import com.edgehub.datahub.parser.HubMessageParser;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

/**
 * Envelope-oriented writer facade.
 * Keeps a single entry for "mqtt envelope -> tdengine write" while preserving existing mapping logic.
 */
@Component
public final class TdengineEnvelopeWriter {

  private final HubMessageParser parser;
  private final TdengineWriter writer;

  public TdengineEnvelopeWriter(HubMessageParser parser, TdengineWriter writer) {
    this.parser = parser;
    this.writer = writer;
  }

  public Mono<Void> write(MqttEnvelope envelope) {
    return parser.parse(envelope.asRawMessage()).flatMap(this::writeParsed);
  }

  public Mono<Void> writeParsed(ParsedHubMessage message) {
    if (message instanceof ParsedHubMessage.TelemetryMessage telemetry) {
      return writer.writeTelemetry(telemetry);
    }
    if (message instanceof ParsedHubMessage.ParameterSetMessage parameterSet) {
      return writer.writeParameterSet(parameterSet);
    }
    if (message instanceof ParsedHubMessage.ParameterAckMessage parameterAck) {
      return writer.writeParameterAck(parameterAck);
    }
    return Mono.empty();
  }
}

