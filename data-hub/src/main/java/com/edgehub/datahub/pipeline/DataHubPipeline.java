package com.edgehub.datahub.pipeline;

import com.edgehub.datahub.config.HubProperties;
import com.edgehub.datahub.model.ParsedHubMessage;
import com.edgehub.datahub.mqtt.MqttMessageSource;
import com.edgehub.datahub.parser.HubMessageParser;
import com.edgehub.datahub.storage.TdengineWriter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;

@Service
public final class DataHubPipeline {

  private static final Logger log = LoggerFactory.getLogger(DataHubPipeline.class);

  private final MqttMessageSource source;
  private final HubMessageParser parser;
  private final TdengineWriter writer;
  private final HubProperties properties;
  private Disposable subscription;

  public DataHubPipeline(
      MqttMessageSource source,
      HubMessageParser parser,
      TdengineWriter writer,
      HubProperties properties) {
    this.source = source;
    this.parser = parser;
    this.writer = writer;
    this.properties = properties;
  }

  public Mono<Void> start() {
    return Mono.fromRunnable(() -> subscription = source.messages()
        .flatMap(message -> parser.parse(message)
                .doOnError(error -> log.warn("message parse failed topic={} payload={}", message.topic(), message.payload(), error))
                .onErrorResume(error -> Mono.empty()),
            properties.getProcessingConcurrency())
        .flatMap(this::persist, properties.getProcessingConcurrency())
        .doOnError(error -> log.error("data hub pipeline processing error", error))
        .retry()
        .subscribe());
  }

  public Mono<Void> stop() {
    return Mono.fromRunnable(() -> {
      if (subscription != null && !subscription.isDisposed()) {
        subscription.dispose();
      }
    });
  }

  private Mono<Void> persist(ParsedHubMessage message) {
    if (message instanceof ParsedHubMessage.TelemetryMessage telemetry) {
      return writer.writeTelemetry(telemetry);
    }
    if (message instanceof ParsedHubMessage.ParameterSetMessage paramsSet) {
      return writer.writeParameterSet(paramsSet);
    }
    if (message instanceof ParsedHubMessage.ParameterAckMessage paramsAck) {
      return writer.writeParameterAck(paramsAck);
    }
    return Mono.empty();
  }
}
