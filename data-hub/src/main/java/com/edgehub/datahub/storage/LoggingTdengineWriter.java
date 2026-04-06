package com.edgehub.datahub.storage;

import com.edgehub.datahub.model.AlarmFactEvent;
import com.edgehub.datahub.model.DeviceStatusSnapshot;
import com.edgehub.datahub.model.ParsedHubMessage;
import com.edgehub.datahub.model.TelemetrySteadySummary;
import com.edgehub.datahub.monitoring.DataHubMetrics;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
@ConditionalOnProperty(prefix = "datahub.storage", name = "mode", havingValue = "log", matchIfMissing = true)
public final class LoggingTdengineWriter implements TdengineWriter {

  private static final Logger log = LoggerFactory.getLogger(LoggingTdengineWriter.class);
  private final DataHubMetrics metrics;

  public LoggingTdengineWriter(DataHubMetrics metrics) {
    this.metrics = metrics;
  }

  @Override
  public Mono<Void> writeTelemetry(ParsedHubMessage.TelemetryMessage telemetry) {
    return Mono.fromRunnable(() -> log.info(
            "tdengine.telemetry device={} runId={} uptimeMs={} targetTemp={} simTemp={} sensorTemp={} controlPeriodMs={} saturationState={} sensorValid={}",
            telemetry.topic().deviceId(),
            telemetry.payload().run_id(),
            telemetry.payload().uptime_ms(),
            telemetry.payload().target_temp_c(),
            telemetry.payload().sim_temp_c(),
            telemetry.payload().sensor_temp_c(),
            telemetry.payload().control_period_ms(),
            telemetry.payload().saturation_state(),
            telemetry.payload().sensor_valid()))
        .doOnSuccess(ignored -> metrics.recordTdengineWriteSuccess())
        .doOnError(ignored -> metrics.recordTdengineWriteFailed())
        .then();
  }

  @Override
  public Mono<Void> writeTelemetrySummary(TelemetrySteadySummary summary) {
    return Mono.fromRunnable(() -> log.info(
            "tdengine.telemetry_summary device={} runId={} samples={} durationMs={} controlPeriodMs={} sensorTempAvg={} absErrorMax={} pwmDutyRange={}-{} flushReason={}",
            summary.deviceId(),
            summary.runId(),
            summary.sampleCount(),
            summary.durationMs(),
            summary.controlPeriodMs(),
            summary.sensorTempAvg(),
            summary.absErrorMax(),
            summary.pwmDutyMin(),
            summary.pwmDutyMax(),
            summary.flushReason()))
        .doOnSuccess(ignored -> metrics.recordTdengineWriteSuccess())
        .doOnError(ignored -> metrics.recordTdengineWriteFailed())
        .then();
  }

  @Override
  public Mono<Void> writeParameterSet(ParsedHubMessage.ParameterSetMessage parameterSet) {
    return Mono.fromRunnable(() -> log.info(
            "tdengine.params_set device={} payload={}",
            parameterSet.topic().deviceId(),
            parameterSet.payload()))
        .doOnSuccess(ignored -> metrics.recordTdengineWriteSuccess())
        .doOnError(ignored -> metrics.recordTdengineWriteFailed())
        .then();
  }

  @Override
  public Mono<Void> writeParameterAck(ParsedHubMessage.ParameterAckMessage parameterAck) {
    return Mono.fromRunnable(() -> log.info(
            "tdengine.params_ack device={} ackType={} success={} reason={}",
            parameterAck.topic().deviceId(),
            parameterAck.payload().ack_type(),
            parameterAck.payload().success(),
            parameterAck.payload().reason()))
        .doOnSuccess(ignored -> metrics.recordTdengineWriteSuccess())
        .doOnError(ignored -> metrics.recordTdengineWriteFailed())
        .then();
  }

  @Override
  public Mono<Void> writeDeviceStatus(DeviceStatusSnapshot status) {
    return Mono.fromRunnable(() -> log.info(
            "tdengine.device_status device={} online={} reason={} lastSeen={} systemState={} lastMessageKind={}",
            status.deviceId(),
            status.online(),
            status.statusReason(),
            status.lastSeenAt(),
            status.systemState(),
            status.lastMessageKind()))
        .doOnSuccess(ignored -> metrics.recordTdengineWriteSuccess())
        .doOnError(ignored -> metrics.recordTdengineWriteFailed())
        .then();
  }

  @Override
  public Mono<Void> writeAlarmFact(AlarmFactEvent alarmFactEvent) {
    return Mono.fromRunnable(() -> log.info(
            "tdengine.alarm_event device={} rule={} type={} severity={} source={} reason={} eventTime={} triggeredAt={} durationSeconds={}",
            alarmFactEvent.deviceId(),
            alarmFactEvent.ruleCode(),
            alarmFactEvent.eventType(),
            alarmFactEvent.severity(),
            alarmFactEvent.source(),
            alarmFactEvent.reason(),
            alarmFactEvent.eventTime(),
            alarmFactEvent.triggeredAt(),
            alarmFactEvent.durationSeconds()))
        .doOnSuccess(ignored -> metrics.recordTdengineWriteSuccess())
        .doOnError(ignored -> metrics.recordTdengineWriteFailed())
        .then();
  }
}
