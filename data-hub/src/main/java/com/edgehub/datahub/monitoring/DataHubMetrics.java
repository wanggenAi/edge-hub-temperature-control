package com.edgehub.datahub.monitoring;

import com.edgehub.datahub.config.HubProperties;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class DataHubMetrics {

  private static final Logger log = LoggerFactory.getLogger(DataHubMetrics.class);

  private final HubProperties properties;

  private final LongAdder ingressReceived = new LongAdder();
  private final LongAdder ingressDropped = new LongAdder();
  private final LongAdder pipelineDropped = new LongAdder();
  private final LongAdder parseFailures = new LongAdder();
  private final LongAdder persistFailures = new LongAdder();
  private final LongAdder telemetrySkipped = new LongAdder();
  private final LongAdder telemetryPersisted = new LongAdder();
  private final LongAdder telemetrySummaryPersisted = new LongAdder();
  private final LongAdder parameterSetPersisted = new LongAdder();
  private final LongAdder parameterAckPersisted = new LongAdder();
  private final LongAdder deviceStatusPersisted = new LongAdder();
  private final LongAdder telemetryFilterStateEvicted = new LongAdder();
  private final LongAdder telemetrySummaryWindowEvicted = new LongAdder();
  private final LongAdder telemetrySummaryWindowDiscarded = new LongAdder();
  private final LongAdder deviceStatusStateEvicted = new LongAdder();

  private final AtomicLong telemetryFilterStateSize = new AtomicLong();
  private final AtomicLong telemetrySummaryWindowSize = new AtomicLong();
  private final AtomicLong deviceStatusStateSize = new AtomicLong();

  private final AtomicLong lastIngressReceived = new AtomicLong();
  private final AtomicLong lastIngressDropped = new AtomicLong();
  private final AtomicLong lastPipelineDropped = new AtomicLong();
  private final AtomicLong lastParseFailures = new AtomicLong();
  private final AtomicLong lastPersistFailures = new AtomicLong();
  private final AtomicLong lastTelemetrySkipped = new AtomicLong();
  private final AtomicLong lastTelemetryPersisted = new AtomicLong();
  private final AtomicLong lastTelemetrySummaryPersisted = new AtomicLong();
  private final AtomicLong lastParameterSetPersisted = new AtomicLong();
  private final AtomicLong lastParameterAckPersisted = new AtomicLong();
  private final AtomicLong lastDeviceStatusPersisted = new AtomicLong();

  public DataHubMetrics(HubProperties properties) {
    this.properties = properties;
  }

  public void recordIngressReceived() {
    ingressReceived.increment();
  }

  public void recordIngressDropped() {
    ingressDropped.increment();
  }

  public void recordPipelineDropped() {
    pipelineDropped.increment();
  }

  public void recordParseFailure() {
    parseFailures.increment();
  }

  public void recordPersistFailure() {
    persistFailures.increment();
  }

  public void recordTelemetrySkipped() {
    telemetrySkipped.increment();
  }

  public void recordTelemetryPersisted() {
    telemetryPersisted.increment();
  }

  public void recordTelemetrySummaryPersisted() {
    telemetrySummaryPersisted.increment();
  }

  public void recordParameterSetPersisted() {
    parameterSetPersisted.increment();
  }

  public void recordParameterAckPersisted() {
    parameterAckPersisted.increment();
  }

  public void recordDeviceStatusPersisted() {
    deviceStatusPersisted.increment();
  }

  public void recordTelemetryFilterStateEvicted() {
    telemetryFilterStateEvicted.increment();
  }

  public void recordTelemetrySummaryWindowEvicted() {
    telemetrySummaryWindowEvicted.increment();
  }

  public void recordTelemetrySummaryWindowDiscarded() {
    telemetrySummaryWindowDiscarded.increment();
  }

  public void updateTelemetryFilterStateSize(long size) {
    telemetryFilterStateSize.set(size);
  }

  public void updateTelemetrySummaryWindowSize(long size) {
    telemetrySummaryWindowSize.set(size);
  }

  public void recordDeviceStatusStateEvicted() {
    deviceStatusStateEvicted.increment();
  }

  public void updateDeviceStatusStateSize(long size) {
    deviceStatusStateSize.set(size);
  }

  @Scheduled(
      initialDelayString = "${datahub.monitoring.stats-log-interval-ms:30000}",
      fixedDelayString = "${datahub.monitoring.stats-log-interval-ms:30000}")
  public void logStats() {
    if (!properties.getMonitoring().isStatsLogEnabled()) {
      return;
    }

    Snapshot total = new Snapshot(
        ingressReceived.sum(),
        ingressDropped.sum(),
        pipelineDropped.sum(),
        parseFailures.sum(),
        persistFailures.sum(),
        telemetrySkipped.sum(),
        telemetryPersisted.sum(),
        telemetrySummaryPersisted.sum(),
        parameterSetPersisted.sum(),
        parameterAckPersisted.sum(),
        deviceStatusPersisted.sum());

    Snapshot delta = new Snapshot(
        total.ingressReceived() - lastIngressReceived.getAndSet(total.ingressReceived()),
        total.ingressDropped() - lastIngressDropped.getAndSet(total.ingressDropped()),
        total.pipelineDropped() - lastPipelineDropped.getAndSet(total.pipelineDropped()),
        total.parseFailures() - lastParseFailures.getAndSet(total.parseFailures()),
        total.persistFailures() - lastPersistFailures.getAndSet(total.persistFailures()),
        total.telemetrySkipped() - lastTelemetrySkipped.getAndSet(total.telemetrySkipped()),
        total.telemetryPersisted() - lastTelemetryPersisted.getAndSet(total.telemetryPersisted()),
        total.telemetrySummaryPersisted() - lastTelemetrySummaryPersisted.getAndSet(total.telemetrySummaryPersisted()),
        total.parameterSetPersisted() - lastParameterSetPersisted.getAndSet(total.parameterSetPersisted()),
        total.parameterAckPersisted() - lastParameterAckPersisted.getAndSet(total.parameterAckPersisted()),
        total.deviceStatusPersisted() - lastDeviceStatusPersisted.getAndSet(total.deviceStatusPersisted()));

    log.info(
        "datahub.stats intervalMs={} delta[recv={} ingressDrop={} pipelineDrop={} parseFail={} persistFail={} telemetrySkip={} telemetryOk={} telemetrySummaryOk={} paramsSetOk={} paramsAckOk={} deviceStatusOk={}] total[recv={} ingressDrop={} pipelineDrop={} parseFail={} persistFail={} telemetrySkip={} telemetryOk={} telemetrySummaryOk={} paramsSetOk={} paramsAckOk={} deviceStatusOk={}] cache[filterSize={} filterEvict={} summarySize={} summaryEvict={} summaryDiscard={} deviceStatusSize={} deviceStatusEvict={}] config[qos={} maxInflight={} sourceQueue={} pipelineBuffer={} parserConcurrency={} writerConcurrency={} prefetch={} overflow={} telemetryFilter={} heartbeatMs={} filterTtlMs={} filterMaxDevices={} telemetrySummary={} summaryMinSamples={} summaryIdleMs={} summaryIdleCheckMs={} summaryTtlMs={} summaryMaxWindows={} deviceStatus={} onlineTimeoutMs={} offlineCheckMs={} deviceStatusTtlMs={} deviceStatusMaxDevices={}]",
        properties.getMonitoring().getStatsLogIntervalMs(),
        delta.ingressReceived(),
        delta.ingressDropped(),
        delta.pipelineDropped(),
        delta.parseFailures(),
        delta.persistFailures(),
        delta.telemetrySkipped(),
        delta.telemetryPersisted(),
        delta.telemetrySummaryPersisted(),
        delta.parameterSetPersisted(),
        delta.parameterAckPersisted(),
        delta.deviceStatusPersisted(),
        total.ingressReceived(),
        total.ingressDropped(),
        total.pipelineDropped(),
        total.parseFailures(),
        total.persistFailures(),
        total.telemetrySkipped(),
        total.telemetryPersisted(),
        total.telemetrySummaryPersisted(),
        total.parameterSetPersisted(),
        total.parameterAckPersisted(),
        total.deviceStatusPersisted(),
        telemetryFilterStateSize.get(),
        telemetryFilterStateEvicted.sum(),
        telemetrySummaryWindowSize.get(),
        telemetrySummaryWindowEvicted.sum(),
        telemetrySummaryWindowDiscarded.sum(),
        deviceStatusStateSize.get(),
        deviceStatusStateEvicted.sum(),
        properties.getMqtt().getQos(),
        properties.getMqtt().getMaxInflight(),
        properties.effectiveSourceQueueSize(),
        properties.getBackpressure().getPipelineBufferSize(),
        properties.effectiveParserConcurrency(),
        properties.effectiveWriterConcurrency(),
        properties.getProcessing().getPrefetch(),
        properties.getBackpressure().getOverflowStrategy(),
        properties.getTelemetryFilter().isEnabled(),
        properties.getTelemetryFilter().getHeartbeatIntervalMs(),
        properties.getTelemetryFilter().getStateTtlMs(),
        properties.getTelemetryFilter().getMaxActiveDevices(),
        properties.getTelemetrySummary().isEnabled(),
        properties.getTelemetrySummary().getMinSamples(),
        properties.getTelemetrySummary().getIdleFlushIntervalMs(),
        properties.getTelemetrySummary().getIdleFlushCheckMs(),
        properties.getTelemetrySummary().getWindowTtlMs(),
        properties.getTelemetrySummary().getMaxActiveWindows(),
        properties.getDeviceStatus().isEnabled(),
        properties.getDeviceStatus().getOnlineTimeoutMs(),
        properties.getDeviceStatus().getOfflineCheckMs(),
        properties.getDeviceStatus().getStateTtlMs(),
        properties.getDeviceStatus().getMaxActiveDevices());
  }

  private record Snapshot(
      long ingressReceived,
      long ingressDropped,
      long pipelineDropped,
      long parseFailures,
      long persistFailures,
      long telemetrySkipped,
      long telemetryPersisted,
      long telemetrySummaryPersisted,
      long parameterSetPersisted,
      long parameterAckPersisted,
      long deviceStatusPersisted) {}
}
