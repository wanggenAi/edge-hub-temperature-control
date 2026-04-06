package com.edgehub.datahub.pipeline;

import com.edgehub.datahub.alarm.AlarmRuleEngineService;
import com.edgehub.datahub.config.HubProperties;
import com.edgehub.datahub.model.AlarmFactEvent;
import com.edgehub.datahub.model.DeviceStatusSnapshot;
import com.edgehub.datahub.model.MqttEnvelope;
import com.edgehub.datahub.model.ParsedHubMessage;
import com.edgehub.datahub.model.TelemetrySteadySummary;
import com.edgehub.datahub.monitoring.DataHubMetrics;
import com.edgehub.datahub.mqtt.MqttMessageSource;
import com.edgehub.datahub.parser.HubMessageParser;
import com.edgehub.datahub.rules.RuleConfigService;
import com.edgehub.datahub.storage.TdengineEnvelopeWriter;
import com.edgehub.datahub.storage.TdengineWriter;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.SmartLifecycle;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import reactor.core.Disposable;
import reactor.core.publisher.BufferOverflowStrategy;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public final class MqttConsumePipeline implements SmartLifecycle {

  private static final Logger log = LoggerFactory.getLogger(MqttConsumePipeline.class);

  private final MqttMessageSource source;
  private final HubMessageParser parser;
  private final TdengineWriter writer;
  private final TdengineEnvelopeWriter envelopeWriter;
  private final HubProperties properties;
  private final DataHubMetrics metrics;
  private final TelemetryWriteFilter telemetryWriteFilter;
  private final TelemetrySummaryAggregator telemetrySummaryAggregator;
  private final DeviceStatusTracker deviceStatusTracker;
  private final AlarmRuleEngineService alarmRuleEngineService;
  private final RuleConfigService ruleConfigService;
  private final AtomicLong pipelineDropped = new AtomicLong();
  private final AtomicLong parseFailures = new AtomicLong();
  private final AtomicLong persistFailures = new AtomicLong();
  private final AtomicBoolean running = new AtomicBoolean();
  private volatile String pipelineOverflowStrategyName = "drop_latest";
  private Disposable subscription;

  public MqttConsumePipeline(
      MqttMessageSource source,
      HubMessageParser parser,
      TdengineWriter writer,
      TdengineEnvelopeWriter envelopeWriter,
      HubProperties properties,
      DataHubMetrics metrics,
      TelemetryWriteFilter telemetryWriteFilter,
      TelemetrySummaryAggregator telemetrySummaryAggregator,
      DeviceStatusTracker deviceStatusTracker,
      AlarmRuleEngineService alarmRuleEngineService,
      RuleConfigService ruleConfigService) {
    this.source = source;
    this.parser = parser;
    this.writer = writer;
    this.envelopeWriter = envelopeWriter;
    this.properties = properties;
    this.metrics = metrics;
    this.telemetryWriteFilter = telemetryWriteFilter;
    this.telemetrySummaryAggregator = telemetrySummaryAggregator;
    this.deviceStatusTracker = deviceStatusTracker;
    this.alarmRuleEngineService = alarmRuleEngineService;
    this.ruleConfigService = ruleConfigService;
  }

  @Override
  public synchronized void start() {
    if (running.get()) {
      return;
    }
    subscription = buildSubscription();
    try {
      source.connect().block();
      running.set(true);
      log.info("mqtt consume pipeline started");
    } catch (RuntimeException exception) {
      if (subscription != null && !subscription.isDisposed()) {
        subscription.dispose();
      }
      subscription = null;
      throw exception;
    }
  }

  @Override
  public synchronized void stop() {
    if (!running.getAndSet(false)) {
      return;
    }
    try {
      source.disconnect().block();
    } catch (RuntimeException exception) {
      log.warn("mqtt source disconnect failed during shutdown", exception);
    }
    flushSummaries(telemetrySummaryAggregator.flushAll("shutdown"), "shutdown");
    if (subscription != null && !subscription.isDisposed()) {
      subscription.dispose();
    }
    subscription = null;
    log.info("mqtt consume pipeline stopped");
  }

  @Override
  public void stop(Runnable callback) {
    try {
      stop();
    } finally {
      callback.run();
    }
  }

  @Override
  public boolean isAutoStartup() {
    return true;
  }

  @Override
  public boolean isRunning() {
    return running.get();
  }

  @Override
  public int getPhase() {
    return 0;
  }

  @Scheduled(
      initialDelayString = "${datahub.telemetry-summary.idle-flush-check-ms:10000}",
      fixedDelayString = "${datahub.telemetry-summary.idle-flush-check-ms:10000}")
  public void flushIdleSummaries() {
    if (!running.get()) {
      return;
    }
    flushSummaries(telemetrySummaryAggregator.flushIdle(Instant.now()), "idle-check");
  }

  @Scheduled(
      initialDelayString = "${datahub.device-status.offline-check-ms:10000}",
      fixedDelayString = "${datahub.device-status.offline-check-ms:10000}")
  public void flushOfflineStatuses() {
    if (!running.get()) {
      return;
    }
    flushDeviceStatuses(deviceStatusTracker.flushOffline(Instant.now()), "offline-check");
  }

  private Disposable buildSubscription() {
    int prefetch = properties.getProcessing().getPrefetch();
    int pipelineBufferSize = properties.getBackpressure().getPipelineBufferSize();
    int laneParallelism = Math.max(1, properties.getMqtt().getDeviceParallelism());
    BufferOverflowStrategy overflowStrategy = resolveOverflowStrategy();
    pipelineOverflowStrategyName = canonicalOverflowStrategyName(overflowStrategy);

    return source.messages()
        .onBackpressureBuffer(
            pipelineBufferSize,
            this::logPipelineDrop,
            overflowStrategy)
        .publishOn(Schedulers.parallel(), prefetch)
        // Fixed lane partitioning avoids unbounded groupBy(deviceId) starvation:
        // with many active devices, finite flatMap concurrency can permanently starve later groups.
        .groupBy(envelope -> laneForDevice(envelope.deviceId(), laneParallelism))
        .flatMap(group -> group.concatMap(this::processEnvelope), laneParallelism)
        .doOnSubscribe(ignored -> log.info(
            "mqtt consume pipeline stream started laneParallelism={} prefetch={} pipelineBufferSize={} overflowStrategy={}",
            laneParallelism,
            prefetch,
            pipelineBufferSize,
            overflowStrategy))
        .doOnError(error -> log.error("mqtt consume pipeline fatal error", error))
        .retry()
        .subscribe();
  }

  private int laneForDevice(String deviceId, int laneParallelism) {
    if (laneParallelism <= 1) {
      return 0;
    }
    return Math.floorMod(deviceId == null ? 0 : deviceId.hashCode(), laneParallelism);
  }

  private Mono<Void> processEnvelope(MqttEnvelope envelope) {
    AtomicReference<MessageOutcome> outcome = new AtomicReference<>(MessageOutcome.PERSISTED);
    return parseEnvelope(envelope, outcome)
        .flatMapMany(message -> applyPersistencePolicy(message, outcome))
        .concatMap(instruction -> persist(instruction)
            .doOnError(error -> logPersistFailure(instruction, error)))
        .then(Mono.fromRunnable(envelope::ack).then())
        .doOnSuccess(ignored -> recordOutcomeOnSuccess(envelope, outcome.get()))
        .doOnSuccess(ignored -> log.debug(
            "mqtt ack success topic={} deviceId={} messageId={}",
            envelope.topic(),
            envelope.deviceId(),
            envelope.messageId()))
        .onErrorResume(error -> {
          if (outcome.get() == MessageOutcome.PARSE_FAILED) {
            metrics.recordOutcomeParseFailed();
          } else {
            outcome.set(MessageOutcome.PERSIST_FAILED);
            metrics.recordOutcomePersistFailed();
          }
          log.error(
              "mqtt message processing failed topic={} deviceId={} messageId={} (no ack)",
              envelope.topic(),
              envelope.deviceId(),
              envelope.messageId(),
              error);
          // Ack on failure to prevent QoS1 inflight stall under overload.
          envelope.ack();
          return Mono.<Void>empty();
        });
  }

  private Mono<ParsedHubMessage> parseEnvelope(
      MqttEnvelope envelope,
      AtomicReference<MessageOutcome> outcome) {
    if (ruleConfigService.onConfigTopic(envelope.topic(), envelope.payload())) {
      outcome.set(MessageOutcome.CONTROL_TOPIC);
      return Mono.empty();
    }
    return parser.parse(envelope.asRawMessage())
        .doOnError(error -> {
          outcome.set(MessageOutcome.PARSE_FAILED);
          logParseFailure(envelope, error);
        });
  }

  private Mono<Void> persist(ParsedHubMessage message) {
    return envelopeWriter.writeParsed(message)
        .doOnSuccess(ignored -> {
          if (message instanceof ParsedHubMessage.TelemetryMessage) {
            metrics.recordTelemetryPersisted();
          } else if (message instanceof ParsedHubMessage.ParameterSetMessage) {
            metrics.recordParameterSetPersisted();
          } else if (message instanceof ParsedHubMessage.ParameterAckMessage) {
            metrics.recordParameterAckPersisted();
          }
        });
  }

  private Mono<Void> persist(PersistenceInstruction instruction) {
    if (instruction instanceof MessageInstruction messageInstruction) {
      return persist(messageInstruction.message());
    }
    if (instruction instanceof TelemetrySummaryInstruction summaryInstruction) {
      return writer.writeTelemetrySummary(summaryInstruction.summary())
          .doOnSuccess(ignored -> metrics.recordTelemetrySummaryPersisted());
    }
    if (instruction instanceof DeviceStatusInstruction deviceStatusInstruction) {
      return writer.writeDeviceStatus(deviceStatusInstruction.status())
          .doOnSuccess(ignored -> metrics.recordDeviceStatusPersisted());
    }
    if (instruction instanceof AlarmFactInstruction alarmFactInstruction) {
      return writer.writeAlarmFact(alarmFactInstruction.alarmFactEvent());
    }
    return Mono.empty();
  }

  private Flux<PersistenceInstruction> applyPersistencePolicy(
      ParsedHubMessage message,
      AtomicReference<MessageOutcome> outcome) {
    List<AlarmFactEvent> alarmEvents = alarmRuleEngineService.onMessage(message);
    DeviceStatusTracker.StatusBatch statusBatch = deviceStatusTracker.onMessage(message);
    if (message instanceof ParsedHubMessage.TelemetryMessage telemetry) {
      TelemetryWriteFilter.FilterDecision decision = telemetryWriteFilter.evaluate(telemetry);
      TelemetrySummaryAggregator.SummaryBatch summaryBatch = telemetrySummaryAggregator.onTelemetry(telemetry, decision);
      if (!decision.persist()) {
        outcome.set(MessageOutcome.TELEMETRY_SKIPPED);
        return alarmInstruction(alarmEvents)
            .concatWith(statusInstruction(statusBatch.updates()))
            .concatWith(summaryInstruction(summaryBatch.summaries()));
      }
      return alarmInstruction(alarmEvents)
          .concatWith(statusInstruction(statusBatch.updates()))
          .concatWith(summaryInstruction(summaryBatch.summaries()))
          .concatWithValues(new MessageInstruction(message));
    }
    if (message instanceof ParsedHubMessage.ParameterSetMessage paramsSet) {
      TelemetrySummaryAggregator.SummaryBatch summaryBatch =
          telemetrySummaryAggregator.flush(paramsSet.topic().deviceId(), "parameter_set");
      telemetryWriteFilter.invalidate(paramsSet.topic().deviceId(), "parameter_set");
      return alarmInstruction(alarmEvents)
          .concatWith(statusInstruction(statusBatch.updates()))
          .concatWith(summaryInstruction(summaryBatch.summaries()))
          .concatWithValues(new MessageInstruction(message));
    }
    if (message instanceof ParsedHubMessage.ParameterAckMessage paramsAck) {
      TelemetrySummaryAggregator.SummaryBatch summaryBatch =
          telemetrySummaryAggregator.flush(paramsAck.topic().deviceId(), "parameter_ack");
      telemetryWriteFilter.invalidate(paramsAck.topic().deviceId(), "parameter_ack");
      return alarmInstruction(alarmEvents)
          .concatWith(statusInstruction(statusBatch.updates()))
          .concatWith(summaryInstruction(summaryBatch.summaries()))
          .concatWithValues(new MessageInstruction(message));
    }
    return alarmInstruction(alarmEvents)
        .concatWith(statusInstruction(statusBatch.updates()))
        .concatWithValues(new MessageInstruction(message));
  }

  private Flux<PersistenceInstruction> alarmInstruction(List<AlarmFactEvent> alarmEvents) {
    if (alarmEvents == null || alarmEvents.isEmpty()) {
      return Flux.empty();
    }
    return Flux.fromIterable(alarmEvents).map(AlarmFactInstruction::new);
  }

  private Flux<PersistenceInstruction> summaryInstruction(List<TelemetrySteadySummary> summaries) {
    if (summaries.isEmpty()) {
      return Flux.empty();
    }
    return Flux.fromIterable(summaries).map(TelemetrySummaryInstruction::new);
  }

  private Flux<PersistenceInstruction> statusInstruction(List<DeviceStatusSnapshot> updates) {
    if (updates.isEmpty()) {
      return Flux.empty();
    }
    Flux<PersistenceInstruction> alarmEvents = Flux.fromIterable(updates)
        .flatMapIterable(alarmRuleEngineService::onDeviceStatus)
        .map(AlarmFactInstruction::new);
    return alarmEvents.concatWith(Flux.fromIterable(updates).map(DeviceStatusInstruction::new));
  }

  private void flushSummaries(List<TelemetrySteadySummary> summaries, String reason) {
    if (summaries.isEmpty()) {
      return;
    }
    log.info("flushing telemetry summaries reason={} count={}", reason, summaries.size());
    for (TelemetrySteadySummary summary : summaries) {
      try {
        writer.writeTelemetrySummary(summary)
            .doOnSuccess(ignored -> metrics.recordTelemetrySummaryPersisted())
            .block();
      } catch (RuntimeException exception) {
        metrics.recordPersistFailure();
        log.error(
            "telemetry summary persist failed deviceId={} flushReason={} persistContext={}",
            summary.deviceId(),
            summary.flushReason(),
            reason,
            exception);
      }
    }
  }

  private void flushDeviceStatuses(List<DeviceStatusSnapshot> statuses, String reason) {
    if (statuses.isEmpty()) {
      return;
    }
    log.info("flushing device status updates reason={} count={}", reason, statuses.size());
    for (DeviceStatusSnapshot status : statuses) {
      try {
        List<AlarmFactEvent> events = alarmRuleEngineService.onDeviceStatus(status);
        for (AlarmFactEvent event : events) {
          writer.writeAlarmFact(event).block();
        }
        writer.writeDeviceStatus(status)
            .doOnSuccess(ignored -> metrics.recordDeviceStatusPersisted())
            .block();
      } catch (RuntimeException exception) {
        metrics.recordPersistFailure();
        log.error(
            "device status persist failed deviceId={} online={} reason={} persistContext={}",
            status.deviceId(),
            status.online(),
            status.statusReason(),
            reason,
            exception);
      }
    }
  }

  private void logPipelineDrop(MqttEnvelope dropped) {
    // Ack dropped messages so inflight window doesn't stall under QoS1.
    dropped.ack();
    metrics.recordMqttDropped();
    metrics.recordPipelineDropped();
    metrics.recordOutcomePipelineDropped();
    long droppedCount = pipelineDropped.incrementAndGet();
    if (droppedCount == 1 || droppedCount % properties.getBackpressure().getOverflowLogEvery() == 0) {
      log.warn(
          "pipeline backpressure drop reason=buffer overflow topic={} deviceId={} messageId={} droppedCount={} strategy={} pipelineBufferSize={}",
          dropped.topic(),
          dropped.deviceId(),
          dropped.messageId(),
          droppedCount,
          pipelineOverflowStrategyName,
          properties.getBackpressure().getPipelineBufferSize());
    }
  }

  private BufferOverflowStrategy resolveOverflowStrategy() {
    String configured = properties.getBackpressure().getOverflowStrategy();
    String normalized = configured == null ? "" : configured.trim().toLowerCase(Locale.ROOT);
    return switch (normalized) {
      case "drop_oldest" -> BufferOverflowStrategy.DROP_OLDEST;
      case "error" -> BufferOverflowStrategy.ERROR;
      case "drop_latest", "" -> BufferOverflowStrategy.DROP_LATEST;
      default -> {
        log.warn(
            "unsupported pipeline overflow strategy={} -> fallback=drop_latest",
            configured);
        yield BufferOverflowStrategy.DROP_LATEST;
      }
    };
  }

  private String canonicalOverflowStrategyName(BufferOverflowStrategy overflowStrategy) {
    return switch (overflowStrategy) {
      case DROP_OLDEST -> "drop_oldest";
      case ERROR -> "error";
      case DROP_LATEST -> "drop_latest";
    };
  }

  private void logParseFailure(MqttEnvelope envelope, Throwable error) {
    metrics.recordParseFailure();
    long failureCount = parseFailures.incrementAndGet();
    log.warn(
        "message parse failed topic={} deviceId={} messageId={} parseFailureCount={} payload={}",
        envelope.topic(),
        envelope.deviceId(),
        envelope.messageId(),
        failureCount,
        envelope.payload(),
        error);
  }

  private void recordOutcomeOnSuccess(MqttEnvelope envelope, MessageOutcome outcome) {
    if (outcome == MessageOutcome.CONTROL_TOPIC) {
      metrics.recordOutcomeControlTopic();
      log.debug(
          "message processed outcome=control_topic topic={} deviceId={} messageId={}",
          envelope.topic(),
          envelope.deviceId(),
          envelope.messageId());
      return;
    }
    if (outcome == MessageOutcome.TELEMETRY_SKIPPED) {
      metrics.recordOutcomeTelemetrySkipped();
      log.debug(
          "message processed outcome=telemetry_skipped topic={} deviceId={} messageId={}",
          envelope.topic(),
          envelope.deviceId(),
          envelope.messageId());
      return;
    }
    metrics.recordOutcomePersisted();
    log.debug(
        "message processed outcome=persisted topic={} deviceId={} messageId={}",
        envelope.topic(),
        envelope.deviceId(),
        envelope.messageId());
  }

  private void logPersistFailure(PersistenceInstruction instruction, Throwable error) {
    metrics.recordPersistFailure();
    long failureCount = persistFailures.incrementAndGet();
    if (instruction instanceof MessageInstruction messageInstruction) {
      ParsedHubMessage message = messageInstruction.message();
      log.error(
          "message persist failed topic={} deviceId={} persistFailureCount={}",
          message.topic().rawTopic(),
          message.topic().deviceId(),
          failureCount,
          error);
      return;
    }
    if (instruction instanceof TelemetrySummaryInstruction summaryInstruction) {
      log.error(
          "telemetry summary persist failed deviceId={} flushReason={} persistFailureCount={}",
          summaryInstruction.summary().deviceId(),
          summaryInstruction.summary().flushReason(),
          failureCount,
          error);
      return;
    }
    if (instruction instanceof DeviceStatusInstruction deviceStatusInstruction) {
      log.error(
          "device status persist failed deviceId={} online={} statusReason={} persistFailureCount={}",
          deviceStatusInstruction.status().deviceId(),
          deviceStatusInstruction.status().online(),
          deviceStatusInstruction.status().statusReason(),
          failureCount,
          error);
      return;
    }
    if (instruction instanceof AlarmFactInstruction alarmFactInstruction) {
      AlarmFactEvent event = alarmFactInstruction.alarmFactEvent();
      log.error(
          "alarm fact persist failed deviceId={} ruleCode={} eventType={} persistFailureCount={}",
          event.deviceId(),
          event.ruleCode(),
          event.eventType(),
          failureCount,
          error);
    }
  }

  private sealed interface PersistenceInstruction
      permits MessageInstruction, TelemetrySummaryInstruction, DeviceStatusInstruction, AlarmFactInstruction {}

  private enum MessageOutcome {
    PERSISTED,
    TELEMETRY_SKIPPED,
    CONTROL_TOPIC,
    PARSE_FAILED,
    PERSIST_FAILED
  }

  private record MessageInstruction(ParsedHubMessage message) implements PersistenceInstruction {}

  private record TelemetrySummaryInstruction(TelemetrySteadySummary summary) implements PersistenceInstruction {}

  private record DeviceStatusInstruction(DeviceStatusSnapshot status) implements PersistenceInstruction {}

  private record AlarmFactInstruction(AlarmFactEvent alarmFactEvent) implements PersistenceInstruction {}
}
