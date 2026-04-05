#pragma once

#include "domain/model/runtime_config.h"

namespace edge::domain {

struct ParameterSetMessage {
  bool has_target_temp_c = false;
  bool has_kp = false;
  bool has_ki = false;
  bool has_kd = false;
  bool has_control_period_ms = false;
  bool has_control_mode = false;
  bool has_apply_immediately = false;

  float target_temp_c = 0.0f;
  float kp = 0.0f;
  float ki = 0.0f;
  float kd = 0.0f;
  uint32_t control_period_ms = 0;
  char control_mode[32] = {};
  bool apply_immediately = false;
};

struct ParameterAckMessage {
  const char* device_id = "";
  const char* ack_type = "";
  bool success = false;
  bool applied_immediately = false;
  bool has_pending_params = false;
  RuntimeControlConfig runtime;
  const char* reason = "";
  unsigned long uptime_ms = 0;
  bool sensor_valid = false;
  bool fault_latched = false;
  const char* fault_reason = "none";
  float software_max_safe_temp_c = 0.0f;
};

}  // namespace edge::domain
