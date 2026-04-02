package com.edgehub.datahub.storage;

import com.edgehub.datahub.model.ParsedHubMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public final class LoggingTdengineWriter implements TdengineWriter {

  private static final Logger log = LoggerFactory.getLogger(LoggingTdengineWriter.class);

  @Override
  public Mono<Void> writeTelemetry(ParsedHubMessage.TelemetryMessage telemetry) {
    return Mono.fromRunnable(() -> log.info(
        "tdengine.telemetry device={} uptimeMs={} targetTemp={} simTemp={} sensorTemp={}",
        telemetry.topic().deviceId(),
        telemetry.payload().uptime_ms(),
        telemetry.payload().target_temp_c(),
        telemetry.payload().sim_temp_c(),
        telemetry.payload().sensor_temp_c()));
  }

  @Override
  public Mono<Void> writeParameterSet(ParsedHubMessage.ParameterSetMessage parameterSet) {
    return Mono.fromRunnable(() -> log.info(
        "tdengine.params_set device={} payload={}",
        parameterSet.topic().deviceId(),
        parameterSet.payload()));
  }

  @Override
  public Mono<Void> writeParameterAck(ParsedHubMessage.ParameterAckMessage parameterAck) {
    return Mono.fromRunnable(() -> log.info(
        "tdengine.params_ack device={} ackType={} success={} reason={}",
        parameterAck.topic().deviceId(),
        parameterAck.payload().ack_type(),
        parameterAck.payload().success(),
        parameterAck.payload().reason()));
  }
}
