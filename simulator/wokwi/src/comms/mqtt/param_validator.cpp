#include "comms/mqtt/param_validator.h"

#include <string.h>

namespace edge::comms::mqtt {

bool ParamValidator::is_control_mode_supported(const char* control_mode) const {
  return strcmp(control_mode, "pid_control") == 0 ||
         strcmp(control_mode, "pi_control") == 0 ||
         strcmp(control_mode, "p_control") == 0;
}

const char* ParamValidator::validate(const edge::domain::ParameterSetMessage& msg) const {
  if (msg.has_target_temp_c &&
      (msg.target_temp_c < limits_.min_target_temp_c ||
       msg.target_temp_c > limits_.max_target_temp_c)) {
    return "target_temp_c_out_of_range";
  }

  if (msg.has_kp && (msg.kp < limits_.min_gain || msg.kp > limits_.max_gain)) {
    return "kp_out_of_range";
  }

  if (msg.has_ki && (msg.ki < limits_.min_gain || msg.ki > limits_.max_gain)) {
    return "ki_out_of_range";
  }

  if (msg.has_kd && (msg.kd < limits_.min_gain || msg.kd > limits_.max_gain)) {
    return "kd_out_of_range";
  }

  if (msg.has_control_period_ms &&
      (msg.control_period_ms < limits_.min_control_period_ms ||
       msg.control_period_ms > limits_.max_control_period_ms)) {
    return "control_period_ms_out_of_range";
  }

  if (msg.has_control_mode && !is_control_mode_supported(msg.control_mode)) {
    return "control_mode_not_supported";
  }

  return "ok";
}

}  // namespace edge::comms::mqtt
