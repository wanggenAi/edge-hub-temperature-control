#include <DallasTemperature.h>
#include <OneWire.h>
#include <PubSubClient.h>
#include <WiFi.h>

namespace Pins {
constexpr uint8_t kOneWireBus = 21;
constexpr uint8_t kStatusLed = 2;
constexpr uint8_t kPwmOutput = 18;
}  // namespace Pins

namespace ControlConfig {
constexpr float kTargetTemperatureC = 35.0f;
constexpr float kProportionalGain = 120.0f;
constexpr float kIntegralGain = 12.0f;
constexpr float kIntegralMin = -20.0f;
constexpr float kIntegralMax = 20.0f;
constexpr unsigned long kControlPeriodMs = 1000;
constexpr unsigned long kHeartbeatPeriodMs = 500;
constexpr uint32_t kPwmFrequencyHz = 5000;
constexpr uint8_t kPwmResolutionBits = 8;
constexpr uint8_t kMaxDuty = 255;
}  // namespace ControlConfig

namespace ThermalModel {
constexpr float kAmbientTemperatureC = 22.0f;
constexpr float kInitialSimTemperatureC = 24.0f;
constexpr float kHeatGainPerCycleC = 1.60f;
constexpr float kCoolingFactor = 0.08f;
}  // namespace ThermalModel

namespace MessagingConfig {
constexpr char kDeviceId[] = "edge-node-001";
constexpr char kControlMode[] = "pi_control";
constexpr char kControllerVersion[] = "pi_tuned_v3_1";
constexpr char kSystemState[] = "running";
constexpr float kDerivativeGain = 0.0f;

constexpr char kTelemetryTopic[] =
    "edge/temperature/edge-node-001/telemetry";
constexpr char kParamsSetTopic[] =
    "edge/temperature/edge-node-001/params/set";
constexpr char kOptimizerRecommendationTopic[] =
    "edge/temperature/edge-node-001/optimizer/recommendation";
}  // namespace MessagingConfig

namespace NetworkConfig {
constexpr char kWifiSsid[] = "Wokwi-GUEST";
constexpr char kWifiPassword[] = "";
constexpr char kMqttHost[] = "broker.emqx.io";
constexpr uint16_t kMqttPort = 1883;
constexpr char kMqttClientId[] = "edge-node-001-sim";
constexpr unsigned long kWifiReconnectIntervalMs = 5000;
constexpr unsigned long kMqttReconnectIntervalMs = 5000;
}  // namespace NetworkConfig

struct TelemetryMessage {
  const char* deviceId;
  unsigned long uptimeMs;
  float targetTempC;
  float simTempC;
  float sensorTempC;
  float errorC;
  float integralError;
  float controlOutput;
  uint8_t pwmDuty;
  float pwmNorm;
  const char* controlMode;
  const char* controllerVersion;
  float kp;
  float ki;
  float kd;
  const char* systemState;
};

struct ParameterSetMessage {
  float targetTempC;
  float kp;
  float ki;
  float kd;
  unsigned long controlPeriodMs;
  const char* controlMode;
  bool applyImmediately;
};

struct OptimizerRecommendationMessage {
  const char* source;
  float recommendedTargetTempC;
  float recommendedKp;
  float recommendedKi;
  float recommendedKd;
  const char* reason;
  float confidence;
  const char* optimizationTag;
};

OneWire oneWire(Pins::kOneWireBus);
DallasTemperature sensors(&oneWire);
WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

unsigned long lastControlMs = 0;
unsigned long lastHeartbeatMs = 0;
unsigned long lastWifiAttemptMs = 0;
unsigned long lastMqttAttemptMs = 0;
bool heartbeatState = false;
bool wifiReadyPrinted = false;

float simulatedTemperatureC = ThermalModel::kInitialSimTemperatureC;
float lastSensorTemperatureC = DEVICE_DISCONNECTED_C;
float accumulatedError = 0.0f;

ParameterSetMessage pendingParams = {
    ControlConfig::kTargetTemperatureC,
    ControlConfig::kProportionalGain,
    ControlConfig::kIntegralGain,
    MessagingConfig::kDerivativeGain,
    ControlConfig::kControlPeriodMs,
    MessagingConfig::kControlMode,
    false,
};

OptimizerRecommendationMessage optimizerRecommendationTemplate = {
    "reserved",
    ControlConfig::kTargetTemperatureC,
    ControlConfig::kProportionalGain,
    ControlConfig::kIntegralGain,
    MessagingConfig::kDerivativeGain,
    "reserved_for_future_optimizer_integration",
    0.0f,
    "not_active",
};

bool setupPwm() {
  const bool pwmReady =
      ledcAttach(Pins::kPwmOutput, ControlConfig::kPwmFrequencyHz,
                 ControlConfig::kPwmResolutionBits);
  if (pwmReady) {
    ledcWrite(Pins::kPwmOutput, 0);
  }
  return pwmReady;
}

float samplePhysicalSensor() {
  sensors.requestTemperatures();
  return sensors.getTempCByIndex(0);
}

float controlPeriodSeconds() {
  return ControlConfig::kControlPeriodMs / 1000.0f;
}

float computeRawControlOutput(float errorC, float integralError) {
  const float proportionalTerm = errorC * ControlConfig::kProportionalGain;
  const float integralTerm = integralError * ControlConfig::kIntegralGain;
  return proportionalTerm + integralTerm;
}

float updateIntegralError(float errorC) {
  const float candidateIntegral =
      constrain(accumulatedError + errorC * controlPeriodSeconds(),
                ControlConfig::kIntegralMin, ControlConfig::kIntegralMax);
  const float candidateOutput = computeRawControlOutput(errorC, candidateIntegral);

  const bool saturatingHigh =
      candidateOutput > ControlConfig::kMaxDuty && errorC > 0.0f;
  const bool saturatingLow = candidateOutput < 0.0f && errorC < 0.0f;

  if (!(saturatingHigh || saturatingLow)) {
    accumulatedError = candidateIntegral;
  }

  return accumulatedError;
}

uint8_t computePwmDuty(float errorC, float integralError, float* controlOutput) {
  const float rawOutput = computeRawControlOutput(errorC, integralError);
  const float clampedOutput =
      constrain(rawOutput, 0.0f, static_cast<float>(ControlConfig::kMaxDuty));

  *controlOutput = clampedOutput;
  return static_cast<uint8_t>(clampedOutput);
}

float dutyToNormalizedLevel(uint8_t duty) {
  return static_cast<float>(duty) / static_cast<float>(ControlConfig::kMaxDuty);
}

float updateSimulatedTemperature(float currentTemperatureC,
                                 float normalizedDuty) {
  const float heatingTerm = ThermalModel::kHeatGainPerCycleC * normalizedDuty;
  const float coolingTerm =
      ThermalModel::kCoolingFactor *
      (currentTemperatureC - ThermalModel::kAmbientTemperatureC);

  return currentTemperatureC + heatingTerm - coolingTerm;
}

TelemetryMessage buildTelemetryMessage(unsigned long nowMs, float simTemperatureC,
                                       float sensorTemperatureC, float errorC,
                                       float integralError,
                                       float controlOutput, uint8_t duty,
                                       float normalizedDuty) {
  TelemetryMessage message = {
      MessagingConfig::kDeviceId,
      nowMs,
      ControlConfig::kTargetTemperatureC,
      simTemperatureC,
      sensorTemperatureC,
      errorC,
      integralError,
      controlOutput,
      duty,
      normalizedDuty,
      MessagingConfig::kControlMode,
      MessagingConfig::kControllerVersion,
      ControlConfig::kProportionalGain,
      ControlConfig::kIntegralGain,
      MessagingConfig::kDerivativeGain,
      MessagingConfig::kSystemState,
  };
  return message;
}

void printControlLog(unsigned long nowMs, float simTemperatureC,
                     float sensorTemperatureC, float errorC,
                     float integralError, float controlOutput, uint8_t duty,
                     float normalizedDuty) {
  Serial.print("time_s=");
  Serial.print(nowMs / 1000.0f, 1);
  Serial.print(", target_c=");
  Serial.print(ControlConfig::kTargetTemperatureC, 2);
  Serial.print(", sim_temp_c=");
  Serial.print(simTemperatureC, 2);
  Serial.print(", sensor_temp_c=");

  if (sensorTemperatureC == DEVICE_DISCONNECTED_C) {
    Serial.print("nan");
  } else {
    Serial.print(sensorTemperatureC, 2);
  }

  Serial.print(", error_c=");
  Serial.print(errorC, 2);
  Serial.print(", integral_error=");
  Serial.print(integralError, 2);
  Serial.print(", control_output=");
  Serial.print(controlOutput, 2);
  Serial.print(", pwm_duty=");
  Serial.print(duty);
  Serial.print(", pwm_norm=");
  Serial.println(normalizedDuty, 3);

  Serial.print("csv,");
  Serial.print(nowMs / 1000.0f, 1);
  Serial.print(",");
  Serial.print(ControlConfig::kTargetTemperatureC, 2);
  Serial.print(",");
  Serial.print(simTemperatureC, 2);
  Serial.print(",");

  if (sensorTemperatureC == DEVICE_DISCONNECTED_C) {
    Serial.print("nan");
  } else {
    Serial.print(sensorTemperatureC, 2);
  }

  Serial.print(",");
  Serial.print(errorC, 2);
  Serial.print(",");
  Serial.print(integralError, 2);
  Serial.print(",");
  Serial.print(controlOutput, 2);
  Serial.print(",");
  Serial.print(duty);
  Serial.print(",");
  Serial.println(normalizedDuty, 3);
}

String telemetryToJson(const TelemetryMessage& message) {
  String payload = "{\"device_id\":\"";
  payload += message.deviceId;
  payload += "\",\"uptime_ms\":";
  payload += String(message.uptimeMs);
  payload += ",\"target_temp_c\":";
  payload += String(message.targetTempC, 2);
  payload += ",\"sim_temp_c\":";
  payload += String(message.simTempC, 2);
  payload += ",\"sensor_temp_c\":";

  if (message.sensorTempC == DEVICE_DISCONNECTED_C) {
    payload += "null";
  } else {
    payload += String(message.sensorTempC, 2);
  }

  payload += ",\"error_c\":";
  payload += String(message.errorC, 2);
  payload += ",\"integral_error\":";
  payload += String(message.integralError, 2);
  payload += ",\"control_output\":";
  payload += String(message.controlOutput, 2);
  payload += ",\"pwm_duty\":";
  payload += String(message.pwmDuty);
  payload += ",\"pwm_norm\":";
  payload += String(message.pwmNorm, 3);
  payload += ",\"control_mode\":\"";
  payload += message.controlMode;
  payload += "\",\"controller_version\":\"";
  payload += message.controllerVersion;
  payload += "\",\"kp\":";
  payload += String(message.kp, 2);
  payload += ",\"ki\":";
  payload += String(message.ki, 2);
  payload += ",\"kd\":";
  payload += String(message.kd, 2);
  payload += ",\"system_state\":\"";
  payload += message.systemState;
  payload += "\"}";
  return payload;
}

void printTelemetryJson(const TelemetryMessage& message) {
  Serial.println(telemetryToJson(message));
}

bool extractFloatField(const String& payload, const char* key, float* value) {
  const String quotedKey = String("\"") + key + "\"";
  const int keyStart = payload.indexOf(quotedKey);
  if (keyStart < 0) {
    return false;
  }

  const int colonIndex = payload.indexOf(':', keyStart + quotedKey.length());
  if (colonIndex < 0) {
    return false;
  }

  int valueStart = colonIndex + 1;
  while (valueStart < payload.length() &&
         (payload[valueStart] == ' ' || payload[valueStart] == '\"')) {
    ++valueStart;
  }

  int valueEnd = valueStart;
  while (valueEnd < payload.length()) {
    const char current = payload[valueEnd];
    if (current == ',' || current == '}' || current == '\"') {
      break;
    }
    ++valueEnd;
  }

  const String numericText = payload.substring(valueStart, valueEnd);
  if (numericText.length() == 0) {
    return false;
  }

  *value = numericText.toFloat();
  return true;
}

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  String payloadText;
  payloadText.reserve(length);

  for (unsigned int index = 0; index < length; ++index) {
    payloadText += static_cast<char>(payload[index]);
  }

  Serial.print("mqtt_rx_topic=");
  Serial.println(topic);
  Serial.print("mqtt_rx_payload=");
  Serial.println(payloadText);

  float parsedTargetTempC = 0.0f;
  if (extractFloatField(payloadText, "target_temp_c", &parsedTargetTempC)) {
    pendingParams.targetTempC = parsedTargetTempC;
    pendingParams.applyImmediately = false;
    Serial.print("pending_target_temp_c=");
    Serial.println(parsedTargetTempC, 2);
    Serial.println("params_apply_mode=reserved_not_applied");
  }
}

void initializeMqttClient() {
  mqttClient.setServer(NetworkConfig::kMqttHost, NetworkConfig::kMqttPort);
  mqttClient.setCallback(onMqttMessage);
}

void ensureWifiConnected(unsigned long nowMs) {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  if (nowMs - lastWifiAttemptMs < NetworkConfig::kWifiReconnectIntervalMs) {
    return;
  }

  lastWifiAttemptMs = nowMs;
  wifiReadyPrinted = false;

  Serial.print("wifi_connecting_ssid=");
  Serial.println(NetworkConfig::kWifiSsid);
  WiFi.mode(WIFI_STA);
  WiFi.begin(NetworkConfig::kWifiSsid, NetworkConfig::kWifiPassword);
}

void ensureMqttConnected(unsigned long nowMs) {
  if (WiFi.status() != WL_CONNECTED || mqttClient.connected()) {
    return;
  }

  if (nowMs - lastMqttAttemptMs < NetworkConfig::kMqttReconnectIntervalMs) {
    return;
  }

  lastMqttAttemptMs = nowMs;

  Serial.print("mqtt_connecting_host=");
  Serial.println(NetworkConfig::kMqttHost);

  if (mqttClient.connect(NetworkConfig::kMqttClientId)) {
    Serial.println("mqtt_status=connected");
    if (mqttClient.subscribe(MessagingConfig::kParamsSetTopic)) {
      Serial.print("mqtt_subscribed_topic=");
      Serial.println(MessagingConfig::kParamsSetTopic);
    } else {
      Serial.print("mqtt_subscribe_failed_topic=");
      Serial.println(MessagingConfig::kParamsSetTopic);
    }
  } else {
    Serial.print("mqtt_connect_failed_state=");
    Serial.println(mqttClient.state());
  }
}

void maintainNetwork(unsigned long nowMs) {
  ensureWifiConnected(nowMs);

  if (WiFi.status() == WL_CONNECTED && !wifiReadyPrinted) {
    wifiReadyPrinted = true;
    Serial.print("wifi_connected_ip=");
    Serial.println(WiFi.localIP());
  }

  ensureMqttConnected(nowMs);

  if (mqttClient.connected()) {
    mqttClient.loop();
  }
}

bool publishTelemetry(const String& payload) {
  if (!mqttClient.connected()) {
    Serial.println("mqtt_publish_skipped=not_connected");
    return false;
  }

  const bool published =
      mqttClient.publish(MessagingConfig::kTelemetryTopic, payload.c_str());
  if (!published) {
    Serial.println("mqtt_publish_status=failed");
  }
  return published;
}

void runControlLoop(unsigned long nowMs) {
  if (nowMs - lastControlMs < ControlConfig::kControlPeriodMs) {
    return;
  }

  lastControlMs = nowMs;
  lastSensorTemperatureC = samplePhysicalSensor();

  const float errorC = ControlConfig::kTargetTemperatureC - simulatedTemperatureC;
  const float integralError = updateIntegralError(errorC);

  float controlOutput = 0.0f;
  const uint8_t duty = computePwmDuty(errorC, integralError, &controlOutput);
  const float normalizedDuty = dutyToNormalizedLevel(duty);

  ledcWrite(Pins::kPwmOutput, duty);
  simulatedTemperatureC =
      updateSimulatedTemperature(simulatedTemperatureC, normalizedDuty);

  printControlLog(nowMs, simulatedTemperatureC, lastSensorTemperatureC, errorC,
                  integralError, controlOutput, duty, normalizedDuty);

  const TelemetryMessage telemetry =
      buildTelemetryMessage(nowMs, simulatedTemperatureC, lastSensorTemperatureC,
                            errorC, integralError, controlOutput, duty,
                            normalizedDuty);
  printTelemetryJson(telemetry);
  publishTelemetry(telemetryToJson(telemetry));
}

void updateHeartbeat(unsigned long nowMs) {
  if (nowMs - lastHeartbeatMs < ControlConfig::kHeartbeatPeriodMs) {
    return;
  }

  lastHeartbeatMs = nowMs;
  heartbeatState = !heartbeatState;
  digitalWrite(Pins::kStatusLed, heartbeatState ? HIGH : LOW);
}

void setup() {
  Serial.begin(115200);
  delay(200);

  Serial.println("boot=edge_temperature_node_v3_1");
  Serial.println("serial_status=ready");

  pinMode(Pins::kStatusLed, OUTPUT);
  digitalWrite(Pins::kStatusLed, LOW);

  sensors.begin();
  sensors.setResolution(12);

  if (!setupPwm()) {
    Serial.println("pwm_init_error=ledcAttach failed");
  }

  initializeMqttClient();

  lastControlMs = millis() - ControlConfig::kControlPeriodMs;
  lastHeartbeatMs = millis();

  Serial.println("edge_temperature_node_v3_1 started");
  Serial.println("control_mode=pi_control");
  Serial.println("control_revision=pi_tuned_v3_1");
  Serial.println("thermal_model=first_order_virtual_heating_cooling");
  Serial.println(
      "csv_header,time_s,target_c,sim_temp_c,sensor_temp_c,error_c,"
      "integral_error,control_output,pwm_duty,pwm_norm");
  Serial.println("telemetry_publish_mode=serial_json_and_mqtt_publish");
  Serial.print("mqtt_broker_host=");
  Serial.println(NetworkConfig::kMqttHost);
  Serial.print("mqtt_telemetry_topic=");
  Serial.println(MessagingConfig::kTelemetryTopic);
  Serial.print("mqtt_params_topic=");
  Serial.println(MessagingConfig::kParamsSetTopic);
}

void loop() {
  const unsigned long nowMs = millis();
  maintainNetwork(nowMs);
  updateHeartbeat(nowMs);
  runControlLoop(nowMs);
  delay(20);
}
