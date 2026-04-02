package com.edgehub.datahub.parser;

import com.edgehub.datahub.model.DeviceTopic;
import com.edgehub.datahub.model.ParameterAckPayload;
import com.edgehub.datahub.model.ParameterSetPayload;
import com.edgehub.datahub.model.ParsedHubMessage;
import com.edgehub.datahub.model.RawMqttMessage;
import com.edgehub.datahub.model.TelemetryPayload;
import com.edgehub.datahub.model.TopicKind;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public final class HubMessageParser {

  private final ObjectMapper objectMapper;

  public HubMessageParser(ObjectMapper objectMapper) {
    this.objectMapper = objectMapper.copy()
        .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
  }

  public Mono<ParsedHubMessage> parse(RawMqttMessage message) {
    return Mono.fromCallable(() -> {
      DeviceTopic topic = DeviceTopic.parseFlexible(message.topic())
          .orElseThrow(() -> new IllegalArgumentException("unsupported topic: " + message.topic()));
      if (topic.kind() == TopicKind.TELEMETRY) {
        TelemetryPayload payload = objectMapper.readValue(message.payload(), TelemetryPayload.class);
        return new ParsedHubMessage.TelemetryMessage(topic, message.receivedAt(), payload);
      }
      if (topic.kind() == TopicKind.PARAMS_SET) {
        ParameterSetPayload payload = objectMapper.readValue(message.payload(), ParameterSetPayload.class);
        return new ParsedHubMessage.ParameterSetMessage(topic, message.receivedAt(), payload);
      }
      ParameterAckPayload payload = objectMapper.readValue(message.payload(), ParameterAckPayload.class);
      return new ParsedHubMessage.ParameterAckMessage(topic, message.receivedAt(), payload);
    });
  }
}
