package com.edgehub.datahub.mqtt;

import com.edgehub.datahub.model.MqttEnvelope;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface MqttMessageSource {

  Mono<Void> connect();

  Flux<MqttEnvelope> messages();

  Mono<Void> disconnect();
}
