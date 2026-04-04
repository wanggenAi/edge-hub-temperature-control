#include "controller/pi_controller.h"

namespace edge::controller {

PiController::PiController(const edge::config::ControlConfig& config) : cfg_(config) {}

edge::domain::ControllerOutput PiController::update(const edge::domain::ControllerInput& in) {
  edge::domain::ControllerOutput out{};

  out.error_c = in.target_temp_c - in.measured_temp_c;

  const float candidate_integral = constrain(
      integral_error_ + out.error_c * in.dt_s,
      cfg_.integral_min,
      cfg_.integral_max);

  const float candidate_output = out.error_c * cfg_.kp + candidate_integral * cfg_.ki;
  const bool saturating_high = candidate_output > cfg_.max_duty && out.error_c > 0.0f;
  const bool saturating_low = candidate_output < 0.0f && out.error_c < 0.0f;

  if (!(saturating_high || saturating_low)) {
    integral_error_ = candidate_integral;
  }

  out.integral_error = integral_error_;

  const float raw_output = out.error_c * cfg_.kp + out.integral_error * cfg_.ki;
  out.control_output = constrain(raw_output, 0.0f, static_cast<float>(cfg_.max_duty));
  out.pwm_duty = static_cast<uint8_t>(out.control_output);
  out.pwm_norm = static_cast<float>(out.pwm_duty) / static_cast<float>(cfg_.max_duty);
  return out;
}

void PiController::reset_integral() { integral_error_ = 0.0f; }

}  // namespace edge::controller
