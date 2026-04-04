#pragma once

#include <Arduino.h>

namespace edge::domain {

enum class FeedbackSourceType {
  kSimulated,
  kSensor,
};

struct TemperatureSample {
  float temperature_c = NAN;
  bool valid = false;
  FeedbackSourceType source = FeedbackSourceType::kSensor;
};

struct ControllerInput {
  float target_temp_c = 0.0f;
  float measured_temp_c = 0.0f;
  float dt_s = 1.0f;
};

struct ControllerOutput {
  float control_output = 0.0f;
  uint8_t pwm_duty = 0;
  float pwm_norm = 0.0f;
  float error_c = 0.0f;
  float integral_error = 0.0f;
};

struct TelemetrySnapshot {
  const char* device_id = "";
  unsigned long uptime_ms = 0;
  float target_temp_c = 0.0f;
  float measured_temp_c = 0.0f;
  float sensor_temp_c = NAN;
  float simulated_temp_c = NAN;
  bool sensor_valid = false;
  bool using_simulated_feedback = false;
  ControllerOutput control;
};

}  // namespace edge::domain
