#pragma once

#include <Arduino.h>

namespace edge::domain {

struct RuntimeControlConfig {
  float target_temp_c = 35.0f;
  float kp = 120.0f;
  float ki = 12.0f;
  float kd = 0.0f;
  uint32_t control_period_ms = 1000;
  char control_mode[32] = "pid_control";
};

}  // namespace edge::domain
