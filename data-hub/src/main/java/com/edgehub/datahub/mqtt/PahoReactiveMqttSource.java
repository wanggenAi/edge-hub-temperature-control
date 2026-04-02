package com.edgehub.datahub.mqtt;

import com.edgehub.datahub.config.HubProperties;
import com.edgehub.datahub.model.RawMqttMessage;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;
import org.eclipse.paho.client.mqttv3.MqttAsyncClient;
import org.eclipse.paho.client.mqttv3.MqttCallback;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

@Component
public final class PahoReactiveMqttSource implements MqttMessageSource {

  private static final Logger log = LoggerFactory.getLogger(PahoReactiveMqttSource.class);

  private final HubProperties properties;
  private final MqttAsyncClient client;
  private final Sinks.Many<RawMqttMessage> sink;

  public PahoReactiveMqttSource(HubProperties properties) {
    this.properties = properties;
    try {
      this.client = new MqttAsyncClient(properties.getMqtt().getUri(), properties.getMqtt().getClientId());
    } catch (MqttException exception) {
      throw new IllegalStateException("failed to initialize mqtt client", exception);
    }
    this.sink = Sinks.many().multicast().onBackpressureBuffer(properties.getBufferSize(), false);
    this.client.setCallback(new CallbackAdapter());
  }

  @Override
  public Mono<Void> connect() {
    return Mono.fromRunnable(() -> {
      try {
        MqttConnectOptions options = new MqttConnectOptions();
        options.setAutomaticReconnect(true);
        options.setCleanSession(true);
        if (!properties.getMqtt().getUsername().isBlank()) {
          options.setUserName(properties.getMqtt().getUsername());
          options.setPassword(properties.getMqtt().getPassword().toCharArray());
        }
        client.connect(options).waitForCompletion();
        client.subscribe("edge/temperature/+/telemetry", 1).waitForCompletion();
        client.subscribe("edge/temperature/+/params/set", 1).waitForCompletion();
        client.subscribe("edge/temperature/+/params/ack", 1).waitForCompletion();
        log.info("mqtt connected and subscribed");
      } catch (MqttException exception) {
        throw new IllegalStateException("failed to connect mqtt source", exception);
      }
    });
  }

  @Override
  public Flux<RawMqttMessage> messages() {
    return sink.asFlux().onBackpressureBuffer(
        properties.getBufferSize(),
        dropped -> log.warn("mqtt inbound buffer overflow, dropping topic={}", dropped.topic()));
  }

  @Override
  public Mono<Void> disconnect() {
    return Mono.fromRunnable(() -> {
      try {
        if (client.isConnected()) {
          client.disconnect().waitForCompletion();
        }
        client.close();
      } catch (MqttException exception) {
        throw new IllegalStateException("failed to disconnect mqtt source", exception);
      }
    });
  }

  private final class CallbackAdapter implements MqttCallback {
    @Override
    public void connectionLost(Throwable cause) {
      log.warn("mqtt connection lost", cause);
    }

    @Override
    public void messageArrived(String topic, MqttMessage message) {
      RawMqttMessage inbound = new RawMqttMessage(
          topic,
          new String(message.getPayload(), StandardCharsets.UTF_8),
          Instant.now());
      Sinks.EmitResult result = sink.tryEmitNext(inbound);
      if (result.isFailure()) {
        log.warn("mqtt inbound emit failed: {} topic={}", result, topic);
      }
    }

    @Override
    public void deliveryComplete(IMqttDeliveryToken token) {
      // The data hub currently consumes only.
    }
  }
}
