#pragma once

namespace edge::domain {

struct RuntimeState {
  float simulated_temp_c = 24.0f;
  float sensor_temp_c = 0.0f;
  bool sensor_valid = false;

  unsigned long last_control_ms = 0;
  unsigned long last_heartbeat_ms = 0;
  bool heartbeat_state = false;
};

}  // namespace edge::domain
