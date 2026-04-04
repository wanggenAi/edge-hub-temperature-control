#include "comms/mqtt/telemetry_builder.h"

#include "comms/mqtt/topic_registry.h"

namespace edge::comms::mqtt {

const char* TelemetryBuilder::saturation_to_text(edge::domain::SaturationState state) const {
  switch (state) {
    case edge::domain::SaturationState::kLow:
      return topic::kSaturationLow;
    case edge::domain::SaturationState::kHigh:
      return topic::kSaturationHigh;
    case edge::domain::SaturationState::kNone:
    default:
      return topic::kSaturationNone;
  }
}

String TelemetryBuilder::to_json(const edge::domain::TelemetrySnapshot& s) const {
  String payload = "{\"device_id\":\"";
  payload += s.device_id;
  payload += "\",\"uptime_ms\":";
  payload += String(s.uptime_ms);
  payload += ",\"target_temp_c\":";
  payload += String(s.target_temp_c, 2);
  payload += ",\"sim_temp_c\":";
  payload += String(s.simulated_temp_c, 2);
  payload += ",\"sensor_temp_c\":";
  payload += s.sensor_valid ? String(s.sensor_temp_c, 2) : String("null");
  payload += ",\"error_c\":";
  payload += String(s.control.error_c, 2);
  payload += ",\"integral_error\":";
  payload += String(s.control.integral_error, 2);
  payload += ",\"control_output\":";
  payload += String(s.control.control_output, 2);
  payload += ",\"pwm_duty\":";
  payload += String(s.control.pwm_duty);
  payload += ",\"pwm_norm\":";
  payload += String(s.control.pwm_norm, 3);
  payload += ",\"control_period_ms\":";
  payload += String(s.control_period_ms);
  payload += ",\"saturation_state\":\"";
  payload += saturation_to_text(s.control.saturation_state);
  payload += "\",\"sensor_valid\":";
  payload += s.sensor_valid ? "true" : "false";
  payload += ",\"run_id\":\"";
  payload += s.run_id;
  payload += "\",\"control_mode\":\"";
  payload += s.control_mode;
  payload += "\",\"controller_version\":\"";
  payload += s.controller_version;
  payload += "\",\"kp\":";
  payload += String(s.kp, 2);
  payload += ",\"ki\":";
  payload += String(s.ki, 2);
  payload += ",\"kd\":";
  payload += String(s.kd, 2);
  payload += ",\"system_state\":\"";
  payload += s.system_state;
  payload += "\",\"has_pending_params\":";
  payload += s.has_pending_params ? "true" : "false";
  payload += ",\"pending_params_age_ms\":";
  payload += String(s.pending_params_age_ms);
  payload += "}";
  return payload;
}

}  // namespace edge::comms::mqtt
