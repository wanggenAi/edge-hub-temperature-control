package com.edgehub.datahub.mqtt;

import com.edgehub.datahub.config.HubProperties;
import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Locale;
import org.springframework.stereotype.Component;

/**
 * Normalized MQTT config for HiveMQ client bootstrap.
 */
@Component
public final class MqttClientConfig {

  private final HubProperties.Mqtt mqtt;
  private final String host;
  private final int port;
  private final boolean ssl;
  private final Duration reconnectDelay;

  public MqttClientConfig(HubProperties properties) {
    this.mqtt = properties.getMqtt();
    URI parsed = URI.create(mqtt.getUri());
    this.host = parsed.getHost() == null ? "127.0.0.1" : parsed.getHost();
    this.ssl = isSslScheme(parsed.getScheme());
    this.port = parsed.getPort() > 0 ? parsed.getPort() : (ssl ? 8883 : 1883);
    this.reconnectDelay = Duration.ofSeconds(Math.max(1, mqtt.getReconnectDelaySeconds()));
  }

  public String host() {
    return host;
  }

  public int port() {
    return port;
  }

  public boolean ssl() {
    return ssl;
  }

  public String clientId() {
    return mqtt.getClientId();
  }

  public String username() {
    return mqtt.getUsername();
  }

  public String password() {
    return mqtt.getPassword();
  }

  public int qos() {
    return mqtt.getQos();
  }

  public int maxInflight() {
    return mqtt.getMaxInflight();
  }

  public int connectTimeoutSeconds() {
    return mqtt.getConnectTimeoutSeconds();
  }

  public int keepAliveSeconds() {
    return mqtt.getKeepAliveSeconds();
  }

  public boolean manualAck() {
    return mqtt.isManualAck();
  }

  public boolean autoReconnect() {
    return mqtt.isAutoReconnect();
  }

  public Duration reconnectDelay() {
    return reconnectDelay;
  }

  public List<String> topicFilters() {
    return mqtt.getTopicFilters();
  }

  public boolean logEachMessage() {
    return mqtt.isLogEachMessage();
  }

  public int deviceParallelism() {
    return mqtt.getDeviceParallelism();
  }

  private boolean isSslScheme(String scheme) {
    if (scheme == null) {
      return false;
    }
    String normalized = scheme.toLowerCase(Locale.ROOT);
    return normalized.equals("ssl") || normalized.equals("tls") || normalized.equals("mqtts");
  }
}

