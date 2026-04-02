package com.edgehub.datahub.mqtt;

import com.edgehub.datahub.model.RawMqttMessage;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface MqttMessageSource {

  Mono<Void> connect();

  Flux<RawMqttMessage> messages();

  Mono<Void> disconnect();
}
