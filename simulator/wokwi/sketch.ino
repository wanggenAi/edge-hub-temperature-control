#include <DallasTemperature.h>
#include <OneWire.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <string.h>

namespace Pins {
constexpr uint8_t kOneWireBus = 21;
constexpr uint8_t kStatusLed = 2;
constexpr uint8_t kPwmOutput = 18;
}  // namespace Pins

namespace ControlConfig {
constexpr float kTargetTemperatureC = 35.0f;
constexpr float kProportionalGain = 120.0f;
constexpr float kIntegralGain = 12.0f;
constexpr float kDerivativeGain = 0.0f;
constexpr float kIntegralMin = -20.0f;
constexpr float kIntegralMax = 20.0f;
constexpr unsigned long kControlPeriodMs = 1000;
constexpr unsigned long kHeartbeatPeriodMs = 500;
constexpr uint32_t kPwmFrequencyHz = 5000;
constexpr uint8_t kPwmResolutionBits = 8;
constexpr uint8_t kMaxDuty = 255;
constexpr float kMinTargetTempC = 20.0f;
constexpr float kMaxTargetTempC = 60.0f;
constexpr float kMinGain = 0.0f;
constexpr float kMaxGain = 1000.0f;
constexpr unsigned long kMinControlPeriodMs = 200;
constexpr unsigned long kMaxControlPeriodMs = 10000;
constexpr size_t kTextFieldSize = 32;
}  // namespace ControlConfig

namespace ThermalModel {
constexpr float kAmbientTemperatureC = 22.0f;
constexpr float kInitialSimTemperatureC = 24.0f;
constexpr float kHeatGainPerCycleC = 1.60f;
constexpr float kCoolingFactor = 0.08f;
}  // namespace ThermalModel

namespace MessagingConfig {
constexpr char kDeviceId[] = "edge-node-001";
constexpr char kDefaultControlMode[] = "pi_control";
constexpr char kControllerVersion[] = "pi_tuned_v3_1";
constexpr char kSystemState[] = "running";

constexpr char kTelemetryTopic[] = "edge/temperature/edge-node-001/telemetry";
constexpr char kParamsSetTopic[] = "edge/temperature/edge-node-001/params/set";
constexpr char kParamsAckTopic[] = "edge/temperature/edge-node-001/params/ack";
constexpr char kOptimizerRecommendationTopic[] =
    "edge/temperature/edge-node-001/optimizer/recommendation";
}  // namespace MessagingConfig

namespace NetworkConfig {
// Update these connection settings when switching from the public test broker
// to a self-managed MQTT server.
// Current Wokwi simulation usually keeps Wi-Fi on `Wokwi-GUEST`.
// For a real deployment, replace the Wi-Fi credentials and MQTT host here.
constexpr char kWifiSsid[] = "Wokwi-GUEST";
constexpr char kWifiPassword[] = "";
constexpr char kMqttHost[] = "38.14.195.2";
constexpr uint16_t kMqttPort = 1883;
// These credentials are used for the current self-managed Mosquitto broker.
// For a different server, update host / username / password here.
constexpr char kMqttUsername[] = "edgeadmin";
constexpr char kMqttPassword[] = "change your password";
constexpr char kMqttClientId[] = "edge-node-001-sim";
constexpr unsigned long kWifiReconnectIntervalMs = 5000;
constexpr unsigned long kMqttReconnectIntervalMs = 5000;
}  // namespace NetworkConfig

struct RuntimeConfig {
  float targetTempC;
  float kp;
  float ki;
  float kd;
  unsigned long controlPeriodMs;
  char controlMode[ControlConfig::kTextFieldSize];
};

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
  bool hasPendingParams;
  unsigned long pendingParamsAgeMs;
};

struct ParameterSetMessage {
  bool hasTargetTempC;
  bool hasKp;
  bool hasKi;
  bool hasKd;
  bool hasControlPeriodMs;
  bool hasControlMode;
  bool hasApplyImmediately;
  float targetTempC;
  float kp;
  float ki;
  float kd;
  unsigned long controlPeriodMs;
  char controlMode[ControlConfig::kTextFieldSize];
  bool applyImmediately;
};

struct ParameterAckMessage {
  const char* deviceId;
  const char* ackType;
  bool success;
  bool appliedImmediately;
  bool hasPendingParams;
  float targetTempC;
  float kp;
  float ki;
  float kd;
  unsigned long controlPeriodMs;
  const char* controlMode;
  const char* reason;
  unsigned long uptimeMs;
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
bool hasPendingParams = false;

float simulatedTemperatureC = ThermalModel::kInitialSimTemperatureC;
float lastSensorTemperatureC = DEVICE_DISCONNECTED_C;
float accumulatedError = 0.0f;
unsigned long pendingParamsReceivedMs = 0;

RuntimeConfig runtimeConfig;
ParameterSetMessage pendingParams = {};

OptimizerRecommendationMessage optimizerRecommendationTemplate = {
    "reserved",
    ControlConfig::kTargetTemperatureC,
    ControlConfig::kProportionalGain,
    ControlConfig::kIntegralGain,
    ControlConfig::kDerivativeGain,
    "reserved_for_future_optimizer_integration",
    0.0f,
    "not_active",
};

void copyText(char* destination, size_t destinationSize, const char* source) {
  if (destinationSize == 0) {
    return;
  }

  strncpy(destination, source, destinationSize - 1);
  destination[destinationSize - 1] = '\0';
}

void initializeRuntimeConfig() {
  runtimeConfig.targetTempC = ControlConfig::kTargetTemperatureC;
  runtimeConfig.kp = ControlConfig::kProportionalGain;
  runtimeConfig.ki = ControlConfig::kIntegralGain;
  runtimeConfig.kd = ControlConfig::kDerivativeGain;
  runtimeConfig.controlPeriodMs = ControlConfig::kControlPeriodMs;
  copyText(runtimeConfig.controlMode, sizeof(runtimeConfig.controlMode),
           MessagingConfig::kDefaultControlMode);
}

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

float controlPeriodSeconds() { return runtimeConfig.controlPeriodMs / 1000.0f; }

float computeRawControlOutput(float errorC, float integralError) {
  const float proportionalTerm = errorC * runtimeConfig.kp;
  const float integralTerm = integralError * runtimeConfig.ki;
  return proportionalTerm + integralTerm;
}

float updateIntegralError(float errorC) {
  const float candidateIntegral =
      constrain(accumulatedError + errorC * controlPeriodSeconds(),
                ControlConfig::kIntegralMin, ControlConfig::kIntegralMax);
  const float candidateOutput =
      computeRawControlOutput(errorC, candidateIntegral);

  const bool saturatingHigh =
      candidateOutput > ControlConfig::kMaxDuty && errorC > 0.0f;
  const bool saturatingLow = candidateOutput < 0.0f && errorC < 0.0f;

  if (!(saturatingHigh || saturatingLow)) {
    accumulatedError = candidateIntegral;
  }

  return accumulatedError;
}

uint8_t computePwmDuty(float errorC, float integralError,
                       float* controlOutput) {
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

TelemetryMessage buildTelemetryMessage(unsigned long nowMs,
                                       float simTemperatureC,
                                       float sensorTemperatureC, float errorC,
                                       float integralError, float controlOutput,
                                       uint8_t duty, float normalizedDuty) {
  TelemetryMessage message = {
      MessagingConfig::kDeviceId,
      nowMs,
      runtimeConfig.targetTempC,
      simTemperatureC,
      sensorTemperatureC,
      errorC,
      integralError,
      controlOutput,
      duty,
      normalizedDuty,
      runtimeConfig.controlMode,
      MessagingConfig::kControllerVersion,
      runtimeConfig.kp,
      runtimeConfig.ki,
      runtimeConfig.kd,
      MessagingConfig::kSystemState,
      hasPendingParams,
      hasPendingParams ? (nowMs - pendingParamsReceivedMs) : 0,
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
  Serial.print(runtimeConfig.targetTempC, 2);
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
  Serial.print(runtimeConfig.targetTempC, 2);
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
  payload += "\",\"has_pending_params\":";
  payload += message.hasPendingParams ? "true" : "false";
  payload += ",\"pending_params_age_ms\":";
  payload += String(message.pendingParamsAgeMs);
  payload += "}";
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

bool extractUnsignedLongField(const String& payload, const char* key,
                              unsigned long* value) {
  float parsedValue = 0.0f;
  if (!extractFloatField(payload, key, &parsedValue)) {
    return false;
  }

  *value = static_cast<unsigned long>(parsedValue);
  return true;
}

bool extractBoolField(const String& payload, const char* key, bool* value) {
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
  while (valueStart < payload.length() && payload[valueStart] == ' ') {
    ++valueStart;
  }

  if (payload.startsWith("true", valueStart)) {
    *value = true;
    return true;
  }

  if (payload.startsWith("false", valueStart)) {
    *value = false;
    return true;
  }

  return false;
}

bool extractStringField(const String& payload, const char* key, char* value,
                        size_t valueSize) {
  const String quotedKey = String("\"") + key + "\"";
  const int keyStart = payload.indexOf(quotedKey);
  if (keyStart < 0) {
    return false;
  }

  const int colonIndex = payload.indexOf(':', keyStart + quotedKey.length());
  if (colonIndex < 0) {
    return false;
  }

  int firstQuoteIndex = payload.indexOf('\"', colonIndex + 1);
  if (firstQuoteIndex < 0) {
    return false;
  }

  const int secondQuoteIndex = payload.indexOf('\"', firstQuoteIndex + 1);
  if (secondQuoteIndex < 0) {
    return false;
  }

  const String parsedText =
      payload.substring(firstQuoteIndex + 1, secondQuoteIndex);
  copyText(value, valueSize, parsedText.c_str());
  return true;
}

bool isControlModeSupported(const char* controlMode) {
  return strcmp(controlMode, "pi_control") == 0 ||
         strcmp(controlMode, "p_control") == 0;
}

void printRuntimeConfigSnapshot() {
  Serial.print("runtime_target_temp_c=");
  Serial.println(runtimeConfig.targetTempC, 2);
  Serial.print("runtime_kp=");
  Serial.println(runtimeConfig.kp, 2);
  Serial.print("runtime_ki=");
  Serial.println(runtimeConfig.ki, 2);
  Serial.print("runtime_kd=");
  Serial.println(runtimeConfig.kd, 2);
  Serial.print("runtime_control_period_ms=");
  Serial.println(runtimeConfig.controlPeriodMs);
  Serial.print("runtime_control_mode=");
  Serial.println(runtimeConfig.controlMode);
}

ParameterAckMessage buildParameterAckMessage(const char* ackType, bool success,
                                             bool appliedImmediately,
                                             bool hasPending,
                                             const char* reason,
                                             unsigned long nowMs) {
  ParameterAckMessage message = {
      MessagingConfig::kDeviceId,
      ackType,
      success,
      appliedImmediately,
      hasPending,
      runtimeConfig.targetTempC,
      runtimeConfig.kp,
      runtimeConfig.ki,
      runtimeConfig.kd,
      runtimeConfig.controlPeriodMs,
      runtimeConfig.controlMode,
      reason,
      nowMs,
  };
  return message;
}

String parameterAckToJson(const ParameterAckMessage& message) {
  String payload = "{\"device_id\":\"";
  payload += message.deviceId;
  payload += "\",\"ack_type\":\"";
  payload += message.ackType;
  payload += "\",\"success\":";
  payload += message.success ? "true" : "false";
  payload += ",\"applied_immediately\":";
  payload += message.appliedImmediately ? "true" : "false";
  payload += ",\"has_pending_params\":";
  payload += message.hasPendingParams ? "true" : "false";
  payload += ",\"target_temp_c\":";
  payload += String(message.targetTempC, 2);
  payload += ",\"kp\":";
  payload += String(message.kp, 2);
  payload += ",\"ki\":";
  payload += String(message.ki, 2);
  payload += ",\"kd\":";
  payload += String(message.kd, 2);
  payload += ",\"control_period_ms\":";
  payload += String(message.controlPeriodMs);
  payload += ",\"control_mode\":\"";
  payload += message.controlMode;
  payload += "\",\"reason\":\"";
  payload += message.reason;
  payload += "\",\"uptime_ms\":";
  payload += String(message.uptimeMs);
  payload += "}";
  return payload;
}

bool publishParameterAck(const ParameterAckMessage& message) {
  const String payload = parameterAckToJson(message);

  Serial.print("mqtt_ack_topic=");
  Serial.println(MessagingConfig::kParamsAckTopic);
  Serial.print("mqtt_ack_payload=");
  Serial.println(payload);

  if (!mqttClient.connected()) {
    Serial.println("mqtt_ack_status=skipped_not_connected");
    return false;
  }

  const bool published =
      mqttClient.publish(MessagingConfig::kParamsAckTopic, payload.c_str());

  Serial.print("mqtt_ack_status=");
  Serial.println(published ? "published" : "failed");
  return published;
}

// Parse supported MQTT params/set fields from a JSON-like payload.
bool parseParameterSetMessage(const String& payload,
                              ParameterSetMessage* message) {
  *message = {};
  bool hasAnyField = false;

  if (extractFloatField(payload, "target_temp_c", &message->targetTempC)) {
    message->hasTargetTempC = true;
    hasAnyField = true;
  }
  if (extractFloatField(payload, "kp", &message->kp)) {
    message->hasKp = true;
    hasAnyField = true;
  }
  if (extractFloatField(payload, "ki", &message->ki)) {
    message->hasKi = true;
    hasAnyField = true;
  }
  if (extractFloatField(payload, "kd", &message->kd)) {
    message->hasKd = true;
    hasAnyField = true;
  }
  if (extractUnsignedLongField(payload, "control_period_ms",
                               &message->controlPeriodMs)) {
    message->hasControlPeriodMs = true;
    hasAnyField = true;
  }
  if (extractStringField(payload, "control_mode", message->controlMode,
                         sizeof(message->controlMode))) {
    message->hasControlMode = true;
    hasAnyField = true;
  }
  if (extractBoolField(payload, "apply_immediately",
                       &message->applyImmediately)) {
    message->hasApplyImmediately = true;
    hasAnyField = true;
  }

  return hasAnyField;
}

bool validateParameterSetMessage(const ParameterSetMessage& message,
                                 const char** failureReason) {
  if (message.hasTargetTempC &&
      (message.targetTempC < ControlConfig::kMinTargetTempC ||
       message.targetTempC > ControlConfig::kMaxTargetTempC)) {
    Serial.println("params_validation_error=target_temp_c_out_of_range");
    *failureReason = "target_temp_c_out_of_range";
    return false;
  }

  if (message.hasKp && (message.kp < ControlConfig::kMinGain ||
                        message.kp > ControlConfig::kMaxGain)) {
    Serial.println("params_validation_error=kp_out_of_range");
    *failureReason = "kp_out_of_range";
    return false;
  }

  if (message.hasKi && (message.ki < ControlConfig::kMinGain ||
                        message.ki > ControlConfig::kMaxGain)) {
    Serial.println("params_validation_error=ki_out_of_range");
    *failureReason = "ki_out_of_range";
    return false;
  }

  if (message.hasKd && (message.kd < ControlConfig::kMinGain ||
                        message.kd > ControlConfig::kMaxGain)) {
    Serial.println("params_validation_error=kd_out_of_range");
    *failureReason = "kd_out_of_range";
    return false;
  }

  if (message.hasControlPeriodMs &&
      (message.controlPeriodMs < ControlConfig::kMinControlPeriodMs ||
       message.controlPeriodMs > ControlConfig::kMaxControlPeriodMs)) {
    Serial.println("params_validation_error=control_period_ms_out_of_range");
    *failureReason = "control_period_ms_out_of_range";
    return false;
  }

  if (message.hasControlMode && !isControlModeSupported(message.controlMode)) {
    Serial.println("params_validation_error=control_mode_not_supported");
    *failureReason = "control_mode_not_supported";
    return false;
  }

  *failureReason = "ok";
  return true;
}

void applyParameterSetMessage(const ParameterSetMessage& message) {
  if (message.hasTargetTempC) {
    runtimeConfig.targetTempC = message.targetTempC;
  }
  if (message.hasKp) {
    runtimeConfig.kp = message.kp;
  }
  if (message.hasKi) {
    runtimeConfig.ki = message.ki;
  }
  if (message.hasKd) {
    runtimeConfig.kd = message.kd;
  }
  if (message.hasControlPeriodMs) {
    runtimeConfig.controlPeriodMs = message.controlPeriodMs;
  }
  if (message.hasControlMode) {
    copyText(runtimeConfig.controlMode, sizeof(runtimeConfig.controlMode),
             message.controlMode);
  }

  Serial.println("params_update_applied=true");
  printRuntimeConfigSnapshot();
}

void applyPendingParamsIfNeeded(unsigned long nowMs) {
  if (!hasPendingParams) {
    return;
  }

  applyParameterSetMessage(pendingParams);
  hasPendingParams = false;
  pendingParamsReceivedMs = 0;
  pendingParams = {};

  Serial.println("pending_params_applied=true");
  Serial.print("pending_params_applied_ms=");
  Serial.println(nowMs);

  publishParameterAck(buildParameterAckMessage(
      "pending_applied", true, false, false, "pending_params_applied", nowMs));
}

// Handle received MQTT params/set payloads and apply runtime config updates.
void handleMqttMessage(char* topic, byte* payload, unsigned int length) {
  String payloadText;
  payloadText.reserve(length);

  for (unsigned int index = 0; index < length; ++index) {
    payloadText += static_cast<char>(payload[index]);
  }

  Serial.print("mqtt_rx_topic=");
  Serial.println(topic);
  Serial.print("mqtt_rx_payload=");
  Serial.println(payloadText);
  Serial.print("params_update_received=");
  Serial.println(payloadText);

  ParameterSetMessage incomingParams;
  if (!parseParameterSetMessage(payloadText, &incomingParams)) {
    Serial.println("params_update_parsed=false");
    publishParameterAck(buildParameterAckMessage(
        "parse_error", false, false, false, "payload_parse_failed", millis()));
    return;
  }

  Serial.println("params_update_parsed=true");

  const char* validationReason = "ok";
  if (!validateParameterSetMessage(incomingParams, &validationReason)) {
    Serial.println("params_update_applied=false");
    publishParameterAck(buildParameterAckMessage(
        "validation_error", false, false, false, validationReason, millis()));
    return;
  }

  if (incomingParams.hasApplyImmediately && incomingParams.applyImmediately) {
    applyParameterSetMessage(incomingParams);
    publishParameterAck(buildParameterAckMessage("applied", true, true, false,
                                                 "applied_ok", millis()));
    return;
  }

  pendingParams = incomingParams;
  hasPendingParams = true;
  pendingParamsReceivedMs = millis();
  Serial.println("params_update_applied=false");
  Serial.println("params_update_staged=true");
  Serial.print("pending_params_received_ms=");
  Serial.println(pendingParamsReceivedMs);
  Serial.println("params_apply_mode=staged_waiting");
  publishParameterAck(buildParameterAckMessage("staged", true, false, true,
                                               "staged_waiting", millis()));
}

void initializeMqttClient() {
  mqttClient.setServer(NetworkConfig::kMqttHost, NetworkConfig::kMqttPort);
  mqttClient.setCallback(handleMqttMessage);
  mqttClient.setBufferSize(512);
}

// Maintain Wi-Fi connectivity without blocking the control loop.
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

// Maintain MQTT connectivity and resubscribe when the broker link is restored.
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

  if (mqttClient.connect(NetworkConfig::kMqttClientId,
                         NetworkConfig::kMqttUsername,
                         NetworkConfig::kMqttPassword)) {
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

// Publish telemetry if MQTT is connected. Skip safely when offline.
bool publishTelemetry(const String& payload) {
  Serial.print("mqtt_publish_payload_len=");
  Serial.println(payload.length());

  if (!mqttClient.connected()) {
    Serial.println("mqtt_publish_skipped=not_connected");
    return false;
  }

  const bool published =
      mqttClient.publish(MessagingConfig::kTelemetryTopic, payload.c_str());
  if (!published) {
    Serial.println("mqtt_publish_status=failed");
  } else {
    Serial.println("mqtt_publish_status=published");
  }
  return published;
}

// Maintain Wi-Fi and MQTT without blocking the control loop.
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

void runControlLoop(unsigned long nowMs) {
  if (nowMs - lastControlMs < runtimeConfig.controlPeriodMs) {
    return;
  }

  lastControlMs = nowMs;
  applyPendingParamsIfNeeded(nowMs);
  lastSensorTemperatureC = samplePhysicalSensor();

  const float errorC = runtimeConfig.targetTempC - simulatedTemperatureC;
  const float integralError = updateIntegralError(errorC);

  float controlOutput = 0.0f;
  const uint8_t duty = computePwmDuty(errorC, integralError, &controlOutput);
  const float normalizedDuty = dutyToNormalizedLevel(duty);

  ledcWrite(Pins::kPwmOutput, duty);
  simulatedTemperatureC =
      updateSimulatedTemperature(simulatedTemperatureC, normalizedDuty);

  printControlLog(nowMs, simulatedTemperatureC, lastSensorTemperatureC, errorC,
                  integralError, controlOutput, duty, normalizedDuty);

  const TelemetryMessage telemetry = buildTelemetryMessage(
      nowMs, simulatedTemperatureC, lastSensorTemperatureC, errorC,
      integralError, controlOutput, duty, normalizedDuty);
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

  initializeRuntimeConfig();

  pinMode(Pins::kStatusLed, OUTPUT);
  digitalWrite(Pins::kStatusLed, LOW);

  sensors.begin();
  sensors.setResolution(12);

  if (!setupPwm()) {
    Serial.println("pwm_init_error=ledcAttach failed");
  }

  initializeMqttClient();

  lastControlMs = millis() - runtimeConfig.controlPeriodMs;
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
  Serial.print("mqtt_broker_port=");
  Serial.println(NetworkConfig::kMqttPort);
  Serial.print("mqtt_username=");
  Serial.println(NetworkConfig::kMqttUsername);
  Serial.print("mqtt_telemetry_topic=");
  Serial.println(MessagingConfig::kTelemetryTopic);
  Serial.print("mqtt_params_topic=");
  Serial.println(MessagingConfig::kParamsSetTopic);
  Serial.print("mqtt_params_ack_topic=");
  Serial.println(MessagingConfig::kParamsAckTopic);
  printRuntimeConfigSnapshot();
}

void loop() {
  const unsigned long nowMs = millis();
  maintainNetwork(nowMs);
  updateHeartbeat(nowMs);
  runControlLoop(nowMs);
  delay(20);
}
