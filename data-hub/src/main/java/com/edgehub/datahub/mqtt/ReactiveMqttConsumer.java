package com.edgehub.datahub.mqtt;

import com.edgehub.datahub.config.HubProperties;
import com.edgehub.datahub.model.DeviceTopic;
import com.edgehub.datahub.model.MqttEnvelope;
import com.edgehub.datahub.monitoring.DataHubMetrics;
import com.hivemq.client.mqtt.datatypes.MqttQos;
import com.hivemq.client.mqtt.lifecycle.MqttDisconnectSource;
import com.hivemq.client.mqtt.mqtt5.Mqtt5AsyncClient;
import com.hivemq.client.mqtt.mqtt5.Mqtt5Client;
import com.hivemq.client.mqtt.mqtt5.message.connect.Mqtt5Connect;
import com.hivemq.client.mqtt.mqtt5.message.publish.Mqtt5Publish;
import com.hivemq.client.mqtt.mqtt5.message.subscribe.Mqtt5Subscribe;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Queue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;
import reactor.util.concurrent.Queues;

@Component
public final class ReactiveMqttConsumer implements MqttMessageSource {

  private static final Logger log = LoggerFactory.getLogger(ReactiveMqttConsumer.class);
  private static final int MAX_NON_SERIALIZED_RETRY = 64;

  private final HubProperties properties;
  private final DataHubMetrics metrics;
  private final MqttClientConfig config;
  private final Mqtt5AsyncClient client;
  private final Sinks.Many<MqttEnvelope> sink;
  private final Queue<MqttEnvelope> sourceQueue;
  private final AtomicLong ingressDropped = new AtomicLong();
  private final AtomicBoolean subscribed = new AtomicBoolean();

  public ReactiveMqttConsumer(HubProperties properties, DataHubMetrics metrics, MqttClientConfig config) {
    this.properties = properties;
    this.metrics = metrics;
    this.config = config;
    this.client = buildClient();
    // Bounded source queue; on overflow we drop the newest message to preserve order and avoid blocking.
    Queue<MqttEnvelope> queue = Queues.<MqttEnvelope>get(properties.effectiveSourceQueueSize()).get();
    this.sourceQueue = queue;
    this.sink = Sinks.many().unicast().onBackpressureBuffer(queue);
  }

  @Override
  public Mono<Void> connect() {
    subscribed.set(false);
    return Mono.fromFuture(() -> client.connect(connectMessage()))
        .timeout(java.time.Duration.ofSeconds(Math.max(1, config.connectTimeoutSeconds())))
        .doOnSuccess(connAck -> log.info(
            "hivemq connected host={} port={} qos={} maxInflight={} sourceQueueSize={}",
            config.host(),
            config.port(),
            config.qos(),
            config.maxInflight(),
            properties.effectiveSourceQueueSize()))
        .then();
  }

  @Override
  public Flux<MqttEnvelope> messages() {
    return sink.asFlux()
        .doOnSubscribe(ignored -> log.info("mqtt source subscriber attached"))
        .doOnCancel(() -> log.warn("mqtt source subscriber cancelled"));
  }

  @Override
  public Mono<Void> disconnect() {
    return Mono.fromFuture(client.disconnect())
        .doOnSuccess(ignored -> log.info("hivemq disconnected"))
        .doFinally(signalType -> subscribed.set(false))
        .onErrorResume(error -> {
          log.warn("hivemq disconnect failed", error);
          return Mono.empty();
        })
        .then();
  }

  private Mqtt5AsyncClient buildClient() {
    var builder = Mqtt5Client.builder()
        .identifier(config.clientId())
        .serverHost(config.host())
        .serverPort(config.port());
    if (config.ssl()) {
      builder.sslWithDefaultConfig();
    }
    if (config.autoReconnect()) {
      builder.automaticReconnect()
          .initialDelay(config.reconnectDelay().toSeconds(), TimeUnit.SECONDS)
          .maxDelay(Math.max(config.reconnectDelay().toSeconds(), 10L), TimeUnit.SECONDS)
          .applyAutomaticReconnect();
    }
    builder.addConnectedListener(context -> log.info(
        "hivemq connected listener clientId={}",
        context.getClientConfig().getClientIdentifier().map(Object::toString).orElse("unknown")));
    // Subscribe from the connected listener only. The HiveMQ client also invokes this
    // listener after automatic reconnects; subscribing again from connect() can register
    // duplicate publish callbacks for the same topic filters in some timing windows.
    builder.addConnectedListener(context -> subscribeTopics()
        .doOnError(error -> log.error("hivemq subscribe after connect failed", error))
        .onErrorResume(error -> Mono.empty())
        .subscribe());
    builder.addDisconnectedListener(context -> {
      if (context.getSource() == MqttDisconnectSource.USER) {
        log.info("hivemq disconnected by user");
        return;
      }
      log.warn(
          "hivemq disconnected source={} cause={}",
          context.getSource(),
          context.getCause() == null ? "n/a" : context.getCause().toString());
    });
    Mqtt5Client client = builder.build();
    return client.toAsync();
  }

  private Mqtt5Connect connectMessage() {
    var builder = Mqtt5Connect.builder()
        .cleanStart(true)
        .keepAlive(Math.max(1, config.keepAliveSeconds()))
        .restrictions()
        .sendMaximum(Math.max(1, config.maxInflight()))
        .receiveMaximum(Math.max(1, config.maxInflight()))
        .applyRestrictions();
    if (!config.username().isBlank()) {
      builder.simpleAuth()
          .username(config.username())
          .password(config.password().getBytes(StandardCharsets.UTF_8))
          .applySimpleAuth();
    }
    return builder.build();
  }

  private Mono<Void> subscribeTopics() {
    if (!subscribed.compareAndSet(false, true)) {
      return Mono.empty();
    }
    return Flux.fromIterable(config.topicFilters())
        .concatMap(topicFilter -> Mono.fromFuture(client.subscribe(
                subscription(topicFilter),
                publish -> onMessage(topicFilter, publish),
                config.manualAck()))
            .doOnSuccess(subAck -> log.info(
                "hivemq subscribed topicFilter={} qos={} manualAck={}",
                topicFilter,
                config.qos(),
                config.manualAck())))
        .doOnError(error -> subscribed.set(false))
        .then();
  }

  private Mqtt5Subscribe subscription(String topicFilter) {
    return Mqtt5Subscribe.builder()
        .addSubscription()
        .topicFilter(topicFilter)
        .qos(MqttQos.fromCode(config.qos()))
        .applySubscription()
        .build();
  }

  private void onMessage(String topicFilter, Mqtt5Publish publish) {
    String topic = publish.getTopic().toString();
    byte[] payloadBytes = publish.getPayloadAsBytes();
    String payload = payloadBytes == null ? "" : new String(payloadBytes, StandardCharsets.UTF_8);
    String deviceId = DeviceTopic.parseFlexible(topic).map(DeviceTopic::deviceId).orElse("unknown");
    MqttEnvelope envelope = new MqttEnvelope(
        topic,
        payload,
        publish.getQos().getCode(),
        publish.isRetain(),
        null,
        deviceId,
        Instant.now(),
        config.manualAck() ? publish::acknowledge : () -> {});
    metrics.recordMqttReceived();
    if (config.logEachMessage()) {
      log.info(
          "mqtt message received topic={} qos={} retained={} deviceId={} payload={}",
          topic,
          envelope.qos(),
          envelope.retain(),
          envelope.deviceId(),
          envelope.payload());
    }
    Sinks.EmitResult result = emitWithShortRetry(envelope);
    metrics.updateCurrentBufferSize(sourceQueue.size());
    if (result.isSuccess()) {
      return;
    }
    // Drop and ack immediately on ingress overflow to avoid stalling QoS1 inflight.
    envelope.ack();
    metrics.recordIngressDropped();
    metrics.recordOutcomeIngressDropped();
    long dropped = ingressDropped.incrementAndGet();
    if (dropped == 1 || dropped % properties.getBackpressure().getOverflowLogEvery() == 0) {
      log.warn(
          "mqtt inbound dropped reason={} topic={} topicFilter={} deviceId={} messageId={} droppedCount={} sourceQueueSize={} emitResult={}",
          result == Sinks.EmitResult.FAIL_OVERFLOW ? "buffer overflow" : "emit failed",
          topic,
          topicFilter,
          deviceId,
          envelope.messageId(),
          dropped,
          properties.effectiveSourceQueueSize(),
          result);
    }
  }

  private Sinks.EmitResult emitWithShortRetry(MqttEnvelope envelope) {
    Sinks.EmitResult result = sink.tryEmitNext(envelope);
    if (result != Sinks.EmitResult.FAIL_NON_SERIALIZED) {
      return result;
    }
    for (int attempt = 0; attempt < MAX_NON_SERIALIZED_RETRY; attempt++) {
      Thread.onSpinWait();
      result = sink.tryEmitNext(envelope);
      if (result != Sinks.EmitResult.FAIL_NON_SERIALIZED) {
        return result;
      }
    }
    return result;
  }
}
