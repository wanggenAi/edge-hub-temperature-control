package com.edgehub.datahub.pipeline;

import com.edgehub.datahub.config.HubProperties;
import com.edgehub.datahub.model.DeviceStatusSnapshot;
import com.edgehub.datahub.model.ParsedHubMessage;
import com.edgehub.datahub.model.RawMqttMessage;
import com.edgehub.datahub.model.TelemetrySteadySummary;
import com.edgehub.datahub.monitoring.DataHubMetrics;
import com.edgehub.datahub.mqtt.MqttMessageSource;
import com.edgehub.datahub.parser.HubMessageParser;
import com.edgehub.datahub.storage.TdengineWriter;
import java.time.Instant;
import java.util.Locale;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.SmartLifecycle;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import reactor.core.publisher.BufferOverflowStrategy;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public final class DataHubPipeline implements SmartLifecycle {

  private static final Logger log = LoggerFactory.getLogger(DataHubPipeline.class);

  private final MqttMessageSource source;
  private final HubMessageParser parser;
  private final TdengineWriter writer;
  private final HubProperties properties;
  private final DataHubMetrics metrics;
  private final TelemetryWriteFilter telemetryWriteFilter;
  private final TelemetrySummaryAggregator telemetrySummaryAggregator;
  private final DeviceStatusTracker deviceStatusTracker;
  private final AtomicLong pipelineDropped = new AtomicLong();
  private final AtomicLong parseFailures = new AtomicLong();
  private final AtomicLong persistFailures = new AtomicLong();
  private final AtomicBoolean running = new AtomicBoolean();
  private Disposable subscription;

  public DataHubPipeline(
      MqttMessageSource source,
      HubMessageParser parser,
      TdengineWriter writer,
      HubProperties properties,
      DataHubMetrics metrics,
      TelemetryWriteFilter telemetryWriteFilter,
      TelemetrySummaryAggregator telemetrySummaryAggregator,
      DeviceStatusTracker deviceStatusTracker) {
    this.source = source;
    this.parser = parser;
    this.writer = writer;
    this.properties = properties;
    this.metrics = metrics;
    this.telemetryWriteFilter = telemetryWriteFilter;
    this.telemetrySummaryAggregator = telemetrySummaryAggregator;
    this.deviceStatusTracker = deviceStatusTracker;
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
      log.info("data hub service started");
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
    log.info("data hub service stopped");
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

  private Mono<Void> persist(ParsedHubMessage message) {
    if (message instanceof ParsedHubMessage.TelemetryMessage telemetry) {
      return writer.writeTelemetry(telemetry)
          .doOnSuccess(ignored -> metrics.recordTelemetryPersisted());
    }
    if (message instanceof ParsedHubMessage.ParameterSetMessage paramsSet) {
      return writer.writeParameterSet(paramsSet)
          .doOnSuccess(ignored -> metrics.recordParameterSetPersisted());
    }
    if (message instanceof ParsedHubMessage.ParameterAckMessage paramsAck) {
      return writer.writeParameterAck(paramsAck)
          .doOnSuccess(ignored -> metrics.recordParameterAckPersisted());
    }
    return Mono.empty();
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
    return Mono.empty();
  }

  private Flux<PersistenceInstruction> applyPersistencePolicy(ParsedHubMessage message) {
    DeviceStatusTracker.StatusBatch statusBatch = deviceStatusTracker.onMessage(message);
    if (message instanceof ParsedHubMessage.TelemetryMessage telemetry) {
      TelemetryWriteFilter.FilterDecision decision = telemetryWriteFilter.evaluate(telemetry);
      TelemetrySummaryAggregator.SummaryBatch summaryBatch = telemetrySummaryAggregator.onTelemetry(telemetry, decision);
      if (!decision.persist()) {
        return statusInstruction(statusBatch.updates()).concatWith(summaryInstruction(summaryBatch.summaries()));
      }
      return statusInstruction(statusBatch.updates())
          .concatWith(summaryInstruction(summaryBatch.summaries()))
          .concatWithValues(new MessageInstruction(message));
    }
    if (message instanceof ParsedHubMessage.ParameterSetMessage paramsSet) {
      TelemetrySummaryAggregator.SummaryBatch summaryBatch =
          telemetrySummaryAggregator.flush(paramsSet.topic().deviceId(), "parameter_set");
      telemetryWriteFilter.invalidate(paramsSet.topic().deviceId(), "parameter_set");
      return statusInstruction(statusBatch.updates())
          .concatWith(summaryInstruction(summaryBatch.summaries()))
          .concatWithValues(new MessageInstruction(message));
    }
    if (message instanceof ParsedHubMessage.ParameterAckMessage paramsAck) {
      TelemetrySummaryAggregator.SummaryBatch summaryBatch =
          telemetrySummaryAggregator.flush(paramsAck.topic().deviceId(), "parameter_ack");
      telemetryWriteFilter.invalidate(paramsAck.topic().deviceId(), "parameter_ack");
      return statusInstruction(statusBatch.updates())
          .concatWith(summaryInstruction(summaryBatch.summaries()))
          .concatWithValues(new MessageInstruction(message));
    }
    return statusInstruction(statusBatch.updates()).concatWithValues(new MessageInstruction(message));
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
    return Flux.fromIterable(updates).map(DeviceStatusInstruction::new);
  }

  private Disposable buildSubscription() {
    int parserConcurrency = properties.effectiveParserConcurrency();
    int writerConcurrency = properties.effectiveWriterConcurrency();
    int prefetch = properties.getProcessing().getPrefetch();
    int pipelineBufferSize = properties.getBackpressure().getPipelineBufferSize();
    BufferOverflowStrategy overflowStrategy =
        resolveOverflowStrategy(properties.getBackpressure().getOverflowStrategy());
    return source.messages()
        .onBackpressureBuffer(
            pipelineBufferSize,
            this::logPipelineDrop,
            overflowStrategy)
        .publishOn(Schedulers.parallel(), prefetch)
        .flatMap(
            message -> parser.parse(message)
                .doOnError(error -> logParseFailure(message, error))
                .onErrorResume(error -> Mono.empty()),
            parserConcurrency,
            prefetch)
        .flatMap(
            this::applyPersistencePolicy,
            parserConcurrency,
            prefetch)
        .flatMap(
            instruction -> persist(instruction)
                .doOnError(error -> logPersistFailure(instruction, error))
                .onErrorResume(error -> Mono.empty()),
            writerConcurrency,
            prefetch)
        .doOnSubscribe(ignored -> log.info(
            "data hub pipeline started parserConcurrency={} writerConcurrency={} prefetch={} pipelineBufferSize={} overflowStrategy={}",
            parserConcurrency,
            writerConcurrency,
            prefetch,
            pipelineBufferSize,
            overflowStrategy))
        .doOnError(error -> log.error("data hub pipeline processing error", error))
        .retry()
        .subscribe();
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

  private void logPipelineDrop(RawMqttMessage dropped) {
    metrics.recordPipelineDropped();
    long droppedCount = pipelineDropped.incrementAndGet();
    if (droppedCount == 1 || droppedCount % properties.getBackpressure().getOverflowLogEvery() == 0) {
      log.warn(
          "pipeline backpressure drop topic={} droppedCount={} strategy={} pipelineBufferSize={}",
          dropped.topic(),
          droppedCount,
          properties.getBackpressure().getOverflowStrategy(),
          properties.getBackpressure().getPipelineBufferSize());
    }
  }

  private void logParseFailure(RawMqttMessage message, Throwable error) {
    metrics.recordParseFailure();
    long failureCount = parseFailures.incrementAndGet();
    log.warn(
        "message parse failed topic={} parseFailureCount={} payload={}",
        message.topic(),
        failureCount,
        message.payload(),
        error);
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
    }
  }

  private BufferOverflowStrategy resolveOverflowStrategy(String strategy) {
    return switch (strategy.toLowerCase(Locale.ROOT)) {
      case "error" -> BufferOverflowStrategy.ERROR;
      case "drop_latest" -> BufferOverflowStrategy.DROP_LATEST;
      case "drop_oldest" -> BufferOverflowStrategy.DROP_OLDEST;
      default -> {
        log.warn("unsupported backpressure overflow strategy '{}', using drop_oldest", strategy);
        yield BufferOverflowStrategy.DROP_OLDEST;
      }
    };
  }

  private sealed interface PersistenceInstruction permits MessageInstruction, TelemetrySummaryInstruction, DeviceStatusInstruction {}

  private record MessageInstruction(ParsedHubMessage message) implements PersistenceInstruction {}

  private record TelemetrySummaryInstruction(TelemetrySteadySummary summary) implements PersistenceInstruction {}

  private record DeviceStatusInstruction(DeviceStatusSnapshot status) implements PersistenceInstruction {}
}
