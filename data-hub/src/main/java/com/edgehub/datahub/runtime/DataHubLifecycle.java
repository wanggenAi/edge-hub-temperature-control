package com.edgehub.datahub.runtime;

import com.edgehub.datahub.mqtt.MqttMessageSource;
import com.edgehub.datahub.pipeline.DataHubPipeline;
import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class DataHubLifecycle implements ApplicationRunner {

  private static final Logger log = LoggerFactory.getLogger(DataHubLifecycle.class);

  private final MqttMessageSource mqttSource;
  private final DataHubPipeline pipeline;

  public DataHubLifecycle(MqttMessageSource mqttSource, DataHubPipeline pipeline) {
    this.mqttSource = mqttSource;
    this.pipeline = pipeline;
  }

  @Override
  public void run(ApplicationArguments args) {
    mqttSource.connect()
        .then(pipeline.start())
        .block(Duration.ofSeconds(10));
    log.info("data hub pipeline started");
  }

  @jakarta.annotation.PreDestroy
  public void shutdown() {
    log.info("shutdown requested");
    pipeline.stop()
        .then(mqttSource.disconnect())
        .block(Duration.ofSeconds(5));
  }
}
