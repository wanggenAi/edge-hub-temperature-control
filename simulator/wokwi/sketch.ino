#include <DallasTemperature.h>
#include <OneWire.h>

namespace Pins {
constexpr uint8_t kOneWireBus = 21;
constexpr uint8_t kStatusLed = 2;
constexpr uint8_t kPwmOutput = 18;
}  // namespace Pins

namespace ControlConfig {
constexpr float kTargetTemperatureC = 35.0f;
constexpr float kProportionalGain = 18.0f;
constexpr unsigned long kControlPeriodMs = 1000;
constexpr unsigned long kHeartbeatPeriodMs = 500;
constexpr uint8_t kPwmChannel = 0;
constexpr uint32_t kPwmFrequencyHz = 5000;
constexpr uint8_t kPwmResolutionBits = 8;
constexpr uint8_t kMaxDuty = 255;
}  // namespace ControlConfig

OneWire oneWire(Pins::kOneWireBus);
DallasTemperature sensors(&oneWire);

unsigned long lastControlMs = 0;
unsigned long lastHeartbeatMs = 0;
bool heartbeatState = false;

void setupPwm() {
  ledcSetup(ControlConfig::kPwmChannel, ControlConfig::kPwmFrequencyHz,
            ControlConfig::kPwmResolutionBits);
  ledcAttachPin(Pins::kPwmOutput, ControlConfig::kPwmChannel);
  ledcWrite(ControlConfig::kPwmChannel, 0);
}

uint8_t computePwmDuty(float errorC) {
  const float proportionalOutput = errorC * ControlConfig::kProportionalGain;
  const float clampedOutput =
      constrain(proportionalOutput, 0.0f, static_cast<float>(ControlConfig::kMaxDuty));
  return static_cast<uint8_t>(clampedOutput);
}

void printControlLog(float currentTemperatureC, float errorC, uint8_t duty) {
  Serial.print("target_c=");
  Serial.print(ControlConfig::kTargetTemperatureC, 2);
  Serial.print(", current_c=");
  Serial.print(currentTemperatureC, 2);
  Serial.print(", error_c=");
  Serial.print(errorC, 2);
  Serial.print(", pwm_duty=");
  Serial.println(duty);
}

void runControlLoop(unsigned long nowMs) {
  if (nowMs - lastControlMs < ControlConfig::kControlPeriodMs) {
    return;
  }

  lastControlMs = nowMs;
  sensors.requestTemperatures();
  const float currentTemperatureC = sensors.getTempCByIndex(0);

  if (currentTemperatureC == DEVICE_DISCONNECTED_C) {
    ledcWrite(ControlConfig::kPwmChannel, 0);
    Serial.println("temperature_read_error=DS18B20 disconnected");
    return;
  }

  const float errorC = ControlConfig::kTargetTemperatureC - currentTemperatureC;
  const uint8_t duty = computePwmDuty(errorC);

  ledcWrite(ControlConfig::kPwmChannel, duty);
  printControlLog(currentTemperatureC, errorC, duty);
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

  pinMode(Pins::kStatusLed, OUTPUT);
  digitalWrite(Pins::kStatusLed, LOW);

  sensors.begin();
  sensors.setResolution(12);
  setupPwm();

  Serial.println("edge_temperature_node_v1 started");
  Serial.println("control_mode=simple_proportional");
}

void loop() {
  const unsigned long nowMs = millis();
  updateHeartbeat(nowMs);
  runControlLoop(nowMs);
}
