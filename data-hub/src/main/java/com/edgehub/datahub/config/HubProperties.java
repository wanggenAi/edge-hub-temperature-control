package com.edgehub.datahub.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "datahub")
public class HubProperties {

  private final Mqtt mqtt = new Mqtt();
  private int bufferSize = 2048;
  private int processingConcurrency = 8;

  public Mqtt getMqtt() {
    return mqtt;
  }

  public int getBufferSize() {
    return bufferSize;
  }

  public void setBufferSize(int bufferSize) {
    this.bufferSize = bufferSize;
  }

  public int getProcessingConcurrency() {
    return processingConcurrency;
  }

  public void setProcessingConcurrency(int processingConcurrency) {
    this.processingConcurrency = processingConcurrency;
  }

  public static class Mqtt {
    private String uri = "tcp://127.0.0.1:1883";
    private String clientId = "java-data-hub-v1";
    private String username = "";
    private String password = "";

    public String getUri() {
      return uri;
    }

    public void setUri(String uri) {
      this.uri = uri;
    }

    public String getClientId() {
      return clientId;
    }

    public void setClientId(String clientId) {
      this.clientId = clientId;
    }

    public String getUsername() {
      return username;
    }

    public void setUsername(String username) {
      this.username = username;
    }

    public String getPassword() {
      return password;
    }

    public void setPassword(String password) {
      this.password = password;
    }
  }
}
