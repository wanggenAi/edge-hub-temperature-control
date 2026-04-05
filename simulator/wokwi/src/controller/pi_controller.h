#pragma once

#include "config/app_config.h"
#include "domain/model/control_types.h"
#include "domain/model/runtime_config.h"

namespace edge::controller {

class PiController {
 public:
  explicit PiController(const edge::config::ControlConfig& config);

  edge::domain::ControllerOutput update(
      const edge::domain::ControllerInput& in,
      const edge::domain::RuntimeControlConfig& runtime);
  void reset_integral();

 private:
  edge::config::ControlConfig cfg_;
  float integral_error_ = 0.0f;
  float previous_error_ = 0.0f;
  bool previous_error_initialized_ = false;
};

}  // namespace edge::controller
