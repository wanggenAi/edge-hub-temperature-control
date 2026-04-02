package com.edgehub.datahub.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "datahub")
public class HubProperties {

  private final Mqtt mqtt = new Mqtt();
  private final Storage storage = new Storage();
  private final Processing processing = new Processing();
  private final Backpressure backpressure = new Backpressure();
  private final TelemetryFilter telemetryFilter = new TelemetryFilter();
  private final TelemetrySummary telemetrySummary = new TelemetrySummary();
  private final Monitoring monitoring = new Monitoring();
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

  public Storage getStorage() {
    return storage;
  }

  public Processing getProcessing() {
    return processing;
  }

  public Backpressure getBackpressure() {
    return backpressure;
  }

  public Monitoring getMonitoring() {
    return monitoring;
  }

  public TelemetryFilter getTelemetryFilter() {
    return telemetryFilter;
  }

  public TelemetrySummary getTelemetrySummary() {
    return telemetrySummary;
  }

  public int getProcessingConcurrency() {
    return processingConcurrency;
  }

  public void setProcessingConcurrency(int processingConcurrency) {
    this.processingConcurrency = processingConcurrency;
  }

  public int effectiveParserConcurrency() {
    return processing.getParserConcurrency() > 0 ? processing.getParserConcurrency() : processingConcurrency;
  }

  public int effectiveWriterConcurrency() {
    return processing.getWriterConcurrency() > 0 ? processing.getWriterConcurrency() : processingConcurrency;
  }

  public int effectiveSourceQueueSize() {
    return backpressure.getSourceQueueSize() > 0 ? backpressure.getSourceQueueSize() : bufferSize;
  }

  public static class Processing {
    private int parserConcurrency = 8;
    private int writerConcurrency = 8;
    private int prefetch = 256;

    public int getParserConcurrency() {
      return parserConcurrency;
    }

    public void setParserConcurrency(int parserConcurrency) {
      this.parserConcurrency = parserConcurrency;
    }

    public int getWriterConcurrency() {
      return writerConcurrency;
    }

    public void setWriterConcurrency(int writerConcurrency) {
      this.writerConcurrency = writerConcurrency;
    }

    public int getPrefetch() {
      return prefetch;
    }

    public void setPrefetch(int prefetch) {
      this.prefetch = prefetch;
    }
  }

  public static class Backpressure {
    private int sourceQueueSize = 2048;
    private int pipelineBufferSize = 4096;
    private String overflowStrategy = "drop_oldest";
    private int overflowLogEvery = 100;

    public int getSourceQueueSize() {
      return sourceQueueSize;
    }

    public void setSourceQueueSize(int sourceQueueSize) {
      this.sourceQueueSize = sourceQueueSize;
    }

    public int getPipelineBufferSize() {
      return pipelineBufferSize;
    }

    public void setPipelineBufferSize(int pipelineBufferSize) {
      this.pipelineBufferSize = pipelineBufferSize;
    }

    public String getOverflowStrategy() {
      return overflowStrategy;
    }

    public void setOverflowStrategy(String overflowStrategy) {
      this.overflowStrategy = overflowStrategy;
    }

    public int getOverflowLogEvery() {
      return overflowLogEvery;
    }

    public void setOverflowLogEvery(int overflowLogEvery) {
      this.overflowLogEvery = overflowLogEvery;
    }
  }

  public static class Storage {
    private String mode = "log";
    private String baseDir = "runtime/data-hub";
    private final Tdengine tdengine = new Tdengine();

    public String getMode() {
      return mode;
    }

    public void setMode(String mode) {
      this.mode = mode;
    }

    public String getBaseDir() {
      return baseDir;
    }

    public void setBaseDir(String baseDir) {
      this.baseDir = baseDir;
    }

    public Tdengine getTdengine() {
      return tdengine;
    }
  }

  public static class Tdengine {
    private String url = "http://127.0.0.1:6041";
    private String database = "edgehub";
    private String username = "root";
    private String password = "taosdata";
    private boolean autoCreate = true;
    private boolean logEachWrite = true;
    private int connectTimeoutSeconds = 5;
    private int requestTimeoutSeconds = 10;

    public String getUrl() {
      return url;
    }

    public void setUrl(String url) {
      this.url = url;
    }

    public String getDatabase() {
      return database;
    }

    public void setDatabase(String database) {
      this.database = database;
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

    public boolean isAutoCreate() {
      return autoCreate;
    }

    public void setAutoCreate(boolean autoCreate) {
      this.autoCreate = autoCreate;
    }

    public boolean isLogEachWrite() {
      return logEachWrite;
    }

    public void setLogEachWrite(boolean logEachWrite) {
      this.logEachWrite = logEachWrite;
    }

    public int getConnectTimeoutSeconds() {
      return connectTimeoutSeconds;
    }

    public void setConnectTimeoutSeconds(int connectTimeoutSeconds) {
      this.connectTimeoutSeconds = connectTimeoutSeconds;
    }

    public int getRequestTimeoutSeconds() {
      return requestTimeoutSeconds;
    }

    public void setRequestTimeoutSeconds(int requestTimeoutSeconds) {
      this.requestTimeoutSeconds = requestTimeoutSeconds;
    }
  }

  public static class Monitoring {
    private boolean statsLogEnabled = true;
    private long statsLogIntervalMs = 30000;

    public boolean isStatsLogEnabled() {
      return statsLogEnabled;
    }

    public void setStatsLogEnabled(boolean statsLogEnabled) {
      this.statsLogEnabled = statsLogEnabled;
    }

    public long getStatsLogIntervalMs() {
      return statsLogIntervalMs;
    }

    public void setStatsLogIntervalMs(long statsLogIntervalMs) {
      this.statsLogIntervalMs = statsLogIntervalMs;
    }
  }

  public static class TelemetryFilter {
    private boolean enabled = false;
    private boolean logSkips = false;
    private long heartbeatIntervalMs = 30000;
    private double targetTempDeadband = 0.05;
    private double simTempDeadband = 0.05;
    private double sensorTempDeadband = 0.05;
    private double errorDeadband = 0.02;
    private double integralErrorDeadband = 1.0;
    private double controlOutputDeadband = 1.0;
    private int pwmDutyDeadband = 1;
    private double pwmNormDeadband = 0.01;
    private double parameterDeadband = 0.01;

    public boolean isEnabled() {
      return enabled;
    }

    public void setEnabled(boolean enabled) {
      this.enabled = enabled;
    }

    public boolean isLogSkips() {
      return logSkips;
    }

    public void setLogSkips(boolean logSkips) {
      this.logSkips = logSkips;
    }

    public long getHeartbeatIntervalMs() {
      return heartbeatIntervalMs;
    }

    public void setHeartbeatIntervalMs(long heartbeatIntervalMs) {
      this.heartbeatIntervalMs = heartbeatIntervalMs;
    }

    public double getTargetTempDeadband() {
      return targetTempDeadband;
    }

    public void setTargetTempDeadband(double targetTempDeadband) {
      this.targetTempDeadband = targetTempDeadband;
    }

    public double getSimTempDeadband() {
      return simTempDeadband;
    }

    public void setSimTempDeadband(double simTempDeadband) {
      this.simTempDeadband = simTempDeadband;
    }

    public double getSensorTempDeadband() {
      return sensorTempDeadband;
    }

    public void setSensorTempDeadband(double sensorTempDeadband) {
      this.sensorTempDeadband = sensorTempDeadband;
    }

    public double getErrorDeadband() {
      return errorDeadband;
    }

    public void setErrorDeadband(double errorDeadband) {
      this.errorDeadband = errorDeadband;
    }

    public double getIntegralErrorDeadband() {
      return integralErrorDeadband;
    }

    public void setIntegralErrorDeadband(double integralErrorDeadband) {
      this.integralErrorDeadband = integralErrorDeadband;
    }

    public double getControlOutputDeadband() {
      return controlOutputDeadband;
    }

    public void setControlOutputDeadband(double controlOutputDeadband) {
      this.controlOutputDeadband = controlOutputDeadband;
    }

    public int getPwmDutyDeadband() {
      return pwmDutyDeadband;
    }

    public void setPwmDutyDeadband(int pwmDutyDeadband) {
      this.pwmDutyDeadband = pwmDutyDeadband;
    }

    public double getPwmNormDeadband() {
      return pwmNormDeadband;
    }

    public void setPwmNormDeadband(double pwmNormDeadband) {
      this.pwmNormDeadband = pwmNormDeadband;
    }

    public double getParameterDeadband() {
      return parameterDeadband;
    }

    public void setParameterDeadband(double parameterDeadband) {
      this.parameterDeadband = parameterDeadband;
    }
  }

  public static class TelemetrySummary {
    private boolean enabled = false;
    private int minSamples = 3;

    public boolean isEnabled() {
      return enabled;
    }

    public void setEnabled(boolean enabled) {
      this.enabled = enabled;
    }

    public int getMinSamples() {
      return minSamples;
    }

    public void setMinSamples(int minSamples) {
      this.minSamples = minSamples;
    }
  }

  public static class Mqtt {
    private String uri = "tcp://127.0.0.1:1883";
    private String clientId = "java-data-hub-v1";
    private String username = "";
    private String password = "";
    private int qos = 1;
    private int maxInflight = 128;
    private int connectTimeoutSeconds = 10;
    private int keepAliveSeconds = 30;

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

    public int getQos() {
      return qos;
    }

    public void setQos(int qos) {
      this.qos = qos;
    }

    public int getMaxInflight() {
      return maxInflight;
    }

    public void setMaxInflight(int maxInflight) {
      this.maxInflight = maxInflight;
    }

    public int getConnectTimeoutSeconds() {
      return connectTimeoutSeconds;
    }

    public void setConnectTimeoutSeconds(int connectTimeoutSeconds) {
      this.connectTimeoutSeconds = connectTimeoutSeconds;
    }

    public int getKeepAliveSeconds() {
      return keepAliveSeconds;
    }

    public void setKeepAliveSeconds(int keepAliveSeconds) {
      this.keepAliveSeconds = keepAliveSeconds;
    }
  }
}
