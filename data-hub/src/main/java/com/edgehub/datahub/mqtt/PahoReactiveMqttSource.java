package com.edgehub.datahub.mqtt;

import com.edgehub.datahub.config.HubProperties;
import com.edgehub.datahub.model.RawMqttMessage;
import com.edgehub.datahub.monitoring.DataHubMetrics;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Queue;
import java.util.concurrent.atomic.AtomicLong;
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;
import org.eclipse.paho.client.mqttv3.MqttAsyncClient;
import org.eclipse.paho.client.mqttv3.MqttCallbackExtended;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;
import reactor.util.concurrent.Queues;

@Component
public final class PahoReactiveMqttSource implements MqttMessageSource {

  private static final Logger log = LoggerFactory.getLogger(PahoReactiveMqttSource.class);

  private final HubProperties properties;
  private final DataHubMetrics metrics;
  private final MqttAsyncClient client;
  private final Sinks.Many<RawMqttMessage> sink;
  private final AtomicLong ingressDropped = new AtomicLong();

  public PahoReactiveMqttSource(HubProperties properties, DataHubMetrics metrics) {
    this.properties = properties;
    this.metrics = metrics;
    try {
      this.client = new MqttAsyncClient(properties.getMqtt().getUri(), properties.getMqtt().getClientId());
    } catch (MqttException exception) {
      throw new IllegalStateException("failed to initialize mqtt client", exception);
    }
    Queue<RawMqttMessage> queue = Queues.<RawMqttMessage>get(properties.effectiveSourceQueueSize()).get();
    this.sink = Sinks.many().unicast().onBackpressureBuffer(queue);
    this.client.setCallback(new CallbackAdapter());
  }

  @Override
  public Mono<Void> connect() {
    return Mono.fromRunnable(() -> {
      try {
        MqttConnectOptions options = new MqttConnectOptions();
        options.setAutomaticReconnect(true);
        options.setCleanSession(true);
        options.setMaxInflight(properties.getMqtt().getMaxInflight());
        options.setConnectionTimeout(properties.getMqtt().getConnectTimeoutSeconds());
        options.setKeepAliveInterval(properties.getMqtt().getKeepAliveSeconds());
        if (!properties.getMqtt().getUsername().isBlank()) {
          options.setUserName(properties.getMqtt().getUsername());
          options.setPassword(properties.getMqtt().getPassword().toCharArray());
        }
        client.connect(options).waitForCompletion();
        subscribeTopics("initial_connect");
        log.info(
            "mqtt connected and subscribed qos={} maxInflight={} sourceQueueSize={}",
            properties.getMqtt().getQos(),
            properties.getMqtt().getMaxInflight(),
            properties.effectiveSourceQueueSize());
      } catch (MqttException exception) {
        throw new IllegalStateException("failed to connect mqtt source", exception);
      }
    });
  }

  @Override
  public Flux<RawMqttMessage> messages() {
    return sink.asFlux()
        .doOnSubscribe(ignored -> log.info("mqtt source subscriber attached"))
        .doOnCancel(() -> log.warn("mqtt source subscriber cancelled"));
  }

  @Override
  public Mono<Void> disconnect() {
    return Mono.fromRunnable(() -> {
      try {
        if (client.isConnected()) {
          client.disconnect().waitForCompletion();
        }
      } catch (MqttException exception) {
        throw new IllegalStateException("failed to disconnect mqtt source", exception);
      }
    });
  }

  private void subscribeTopics(String reason) throws MqttException {
    int qos = properties.getMqtt().getQos();
    client.subscribe("edge/temperature/+/telemetry", qos).waitForCompletion();
    client.subscribe("edge/temperature/+/params/set", qos).waitForCompletion();
    client.subscribe("edge/temperature/+/params/ack", qos).waitForCompletion();
    log.info("mqtt subscriptions active reason={} qos={}", reason, qos);
  }

  private final class CallbackAdapter implements MqttCallbackExtended {
    @Override
    public void connectComplete(boolean reconnect, String serverURI) {
      if (!reconnect) {
        return;
      }
      try {
        subscribeTopics("auto_reconnect");
        log.info("mqtt reconnect complete serverUri={}", serverURI);
      } catch (MqttException exception) {
        log.error("mqtt resubscribe failed after reconnect serverUri={}", serverURI, exception);
      }
    }

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
      metrics.recordIngressReceived();
      Sinks.EmitResult result = sink.tryEmitNext(inbound);
      if (result.isFailure()) {
        metrics.recordIngressDropped();
        long dropped = ingressDropped.incrementAndGet();
        if (dropped == 1 || dropped % properties.getBackpressure().getOverflowLogEvery() == 0) {
          log.warn(
              "mqtt inbound emit failed result={} topic={} droppedCount={} sourceQueueSize={}",
              result,
              topic,
              dropped,
              properties.effectiveSourceQueueSize());
        }
      }
    }

    @Override
    public void deliveryComplete(IMqttDeliveryToken token) {
      // The data hub currently consumes only.
    }
  }
}
