#pragma once

#include "domain/model/param_messages.h"

namespace edge::comms::mqtt {

class AckBuilder {
 public:
  edge::domain::ParameterAckMessage build(const char* device_id,
                                          const edge::domain::RuntimeControlConfig& runtime,
                                          const char* ack_type,
                                          bool success,
                                          bool applied_immediately,
                                          bool has_pending,
                                          const char* reason,
                                          unsigned long now_ms,
                                          bool sensor_valid = false,
                                          bool fault_latched = false,
                                          const char* fault_reason = "none",
                                          float software_max_safe_temp_c = 0.0f) const;

  String to_json(const edge::domain::ParameterAckMessage& message) const;
};

}  // namespace edge::comms::mqtt
