#include <DallasTemperature.h>
#include <OneWire.h>

namespace Pins {
constexpr uint8_t kOneWireBus = 21;
constexpr uint8_t kStatusLed = 2;
constexpr uint8_t kPwmOutput = 18;
}  // namespace Pins

namespace ControlConfig {
constexpr float kTargetTemperatureC = 35.0f;
constexpr float kProportionalGain = 120.0f;
constexpr float kIntegralGain = 10.0f;
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

OneWire oneWire(Pins::kOneWireBus);
DallasTemperature sensors(&oneWire);

unsigned long lastControlMs = 0;
unsigned long lastHeartbeatMs = 0;
bool heartbeatState = false;

float simulatedTemperatureC = ThermalModel::kInitialSimTemperatureC;
float lastSensorTemperatureC = DEVICE_DISCONNECTED_C;
float accumulatedError = 0.0f;

void setupPwm() {
  const bool pwmReady =
      ledcAttach(Pins::kPwmOutput, ControlConfig::kPwmFrequencyHz,
                 ControlConfig::kPwmResolutionBits);

  if (!pwmReady) {
    Serial.println("pwm_init_error=ledcAttach failed");
    return;
  }

  ledcWrite(Pins::kPwmOutput, 0);
}

float controlPeriodSeconds() {
  return ControlConfig::kControlPeriodMs / 1000.0f;
}

float updateIntegralError(float errorC) {
  accumulatedError += errorC * controlPeriodSeconds();
  accumulatedError =
      constrain(accumulatedError, ControlConfig::kIntegralMin,
                ControlConfig::kIntegralMax);
  return accumulatedError;
}

uint8_t computePwmDuty(float errorC, float integralError, float* controlOutput) {
  const float proportionalTerm = errorC * ControlConfig::kProportionalGain;
  const float integralTerm = integralError * ControlConfig::kIntegralGain;
  const float rawOutput = proportionalTerm + integralTerm;
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

void samplePhysicalSensor() {
  sensors.requestTemperatures();
  lastSensorTemperatureC = sensors.getTempCByIndex(0);
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

void runControlLoop(unsigned long nowMs) {
  if (nowMs - lastControlMs < ControlConfig::kControlPeriodMs) {
    return;
  }

  lastControlMs = nowMs;
  samplePhysicalSensor();

  const float errorC =
      ControlConfig::kTargetTemperatureC - simulatedTemperatureC;
  const float integralError = updateIntegralError(errorC);
  float controlOutput = 0.0f;
  const uint8_t duty = computePwmDuty(errorC, integralError, &controlOutput);
  const float normalizedDuty = dutyToNormalizedLevel(duty);

  ledcWrite(Pins::kPwmOutput, duty);
  simulatedTemperatureC =
      updateSimulatedTemperature(simulatedTemperatureC, normalizedDuty);

  printControlLog(nowMs, simulatedTemperatureC, lastSensorTemperatureC, errorC,
                  integralError, controlOutput, duty, normalizedDuty);
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

  Serial.println("boot=edge_temperature_node_v3");
  Serial.println("serial_status=ready");

  pinMode(Pins::kStatusLed, OUTPUT);
  digitalWrite(Pins::kStatusLed, LOW);

  sensors.begin();
  sensors.setResolution(12);
  setupPwm();

  lastControlMs = millis() - ControlConfig::kControlPeriodMs;
  lastHeartbeatMs = millis();

  Serial.println("edge_temperature_node_v3 started");
  Serial.println("control_mode=pi_control");
  Serial.println("thermal_model=first_order_virtual_heating_cooling");
  Serial.println(
      "csv_header,time_s,target_c,sim_temp_c,sensor_temp_c,error_c,"
      "integral_error,control_output,pwm_duty,pwm_norm");
}

void loop() {
  const unsigned long nowMs = millis();
  updateHeartbeat(nowMs);
  runControlLoop(nowMs);
  delay(20);
}
