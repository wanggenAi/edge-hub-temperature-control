#pragma once

#include "config/app_config.h"
#include "domain/model/param_messages.h"

namespace edge::comms::mqtt {

class ParamValidator {
 public:
  explicit ParamValidator(const edge::config::ControlConfig& limits) : limits_(limits) {}

  const char* validate(const edge::domain::ParameterSetMessage& msg) const;

 private:
  bool is_control_mode_supported(const char* control_mode) const;

  edge::config::ControlConfig limits_;
};

}  // namespace edge::comms::mqtt
