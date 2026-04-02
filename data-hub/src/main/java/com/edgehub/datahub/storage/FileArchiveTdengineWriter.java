package com.edgehub.datahub.storage;

import com.edgehub.datahub.config.HubProperties;
import com.edgehub.datahub.model.ParsedHubMessage;
import com.edgehub.datahub.model.TelemetrySteadySummary;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Component
@ConditionalOnProperty(prefix = "datahub.storage", name = "mode", havingValue = "file")
public final class FileArchiveTdengineWriter implements TdengineWriter {

  private static final Logger log = LoggerFactory.getLogger(FileArchiveTdengineWriter.class);

  private final Object writeLock = new Object();
  private final ObjectMapper objectMapper;
  private final Path baseDir;
  private final Path telemetryFile;
  private final Path telemetrySummaryFile;
  private final Path parameterSetFile;
  private final Path parameterAckFile;

  public FileArchiveTdengineWriter(ObjectMapper objectMapper, HubProperties properties) {
    this.objectMapper = objectMapper;
    this.baseDir = Path.of(properties.getStorage().getBaseDir());
    this.telemetryFile = baseDir.resolve("telemetry.jsonl");
    this.telemetrySummaryFile = baseDir.resolve("telemetry-summary.jsonl");
    this.parameterSetFile = baseDir.resolve("params-set.jsonl");
    this.parameterAckFile = baseDir.resolve("params-ack.jsonl");
    createBaseDirectory();
  }

  @Override
  public Mono<Void> writeTelemetry(ParsedHubMessage.TelemetryMessage telemetry) {
    return appendJsonLine(telemetryFile, "telemetry", telemetry.receivedAt(), telemetry.topic().deviceId(), Map.of(
        "topic", telemetry.topic().rawTopic(),
        "payload", telemetry.payload()));
  }

  @Override
  public Mono<Void> writeTelemetrySummary(TelemetrySteadySummary summary) {
    return appendJsonLine(
        telemetrySummaryFile,
        "telemetry_summary",
        summary.windowEnd(),
        summary.deviceId(),
        Map.of(
            "topic", summary.rawTopic(),
            "payload", summary));
  }

  @Override
  public Mono<Void> writeParameterSet(ParsedHubMessage.ParameterSetMessage parameterSet) {
    return appendJsonLine(
        parameterSetFile,
        "params_set",
        parameterSet.receivedAt(),
        parameterSet.topic().deviceId(),
        Map.of(
            "topic", parameterSet.topic().rawTopic(),
            "payload", parameterSet.payload()));
  }

  @Override
  public Mono<Void> writeParameterAck(ParsedHubMessage.ParameterAckMessage parameterAck) {
    return appendJsonLine(
        parameterAckFile,
        "params_ack",
        parameterAck.receivedAt(),
        parameterAck.topic().deviceId(),
        Map.of(
            "topic", parameterAck.topic().rawTopic(),
            "payload", parameterAck.payload()));
  }

  private Mono<Void> appendJsonLine(
      Path targetFile,
      String eventType,
      Instant receivedAt,
      String deviceId,
      Map<String, Object> content) {
    return Mono.fromRunnable(() -> {
          try {
            Map<String, Object> envelope = new LinkedHashMap<>();
            envelope.put("event_type", eventType);
            envelope.put("device_id", deviceId);
            envelope.put("received_at", receivedAt);
            envelope.putAll(content);
            byte[] line = (objectMapper.writeValueAsString(envelope) + System.lineSeparator())
                .getBytes(StandardCharsets.UTF_8);
            synchronized (writeLock) {
              Files.write(
                  targetFile,
                  line,
                  StandardOpenOption.CREATE,
                  StandardOpenOption.WRITE,
                  StandardOpenOption.APPEND);
            }
          } catch (IOException exception) {
            throw new IllegalStateException("failed to append archive file: " + targetFile, exception);
          }
        })
        .doOnSuccess(ignored -> log.debug("archived {} event to {}", eventType, targetFile))
        .subscribeOn(Schedulers.boundedElastic())
        .then();
  }

  private void createBaseDirectory() {
    try {
      Files.createDirectories(baseDir);
    } catch (IOException exception) {
      throw new IllegalStateException("failed to create archive directory: " + baseDir, exception);
    }
  }
}
