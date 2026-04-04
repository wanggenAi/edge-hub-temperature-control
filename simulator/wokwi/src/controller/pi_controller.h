#pragma once

#include "config/app_config.h"
#include "domain/model/control_types.h"

namespace edge::controller {

class PiController {
 public:
  explicit PiController(const edge::config::ControlConfig& config);

  edge::domain::ControllerOutput update(const edge::domain::ControllerInput& in);
  void reset_integral();

 private:
  edge::config::ControlConfig cfg_;
  float integral_error_ = 0.0f;
};

}  // namespace edge::controller
