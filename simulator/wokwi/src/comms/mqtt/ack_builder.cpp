#include "comms/mqtt/ack_builder.h"

namespace edge::comms::mqtt {

edge::domain::ParameterAckMessage AckBuilder::build(
    const char* device_id,
    const edge::domain::RuntimeControlConfig& runtime,
    const char* ack_type,
    bool success,
    bool applied_immediately,
    bool has_pending,
    const char* reason,
    unsigned long now_ms,
    bool sensor_valid,
    bool fault_latched,
    const char* fault_reason,
    float software_max_safe_temp_c) const {
  edge::domain::ParameterAckMessage message{};
  message.device_id = device_id;
  message.ack_type = ack_type;
  message.success = success;
  message.applied_immediately = applied_immediately;
  message.has_pending_params = has_pending;
  message.runtime = runtime;
  message.reason = reason;
  message.uptime_ms = now_ms;
  message.sensor_valid = sensor_valid;
  message.fault_latched = fault_latched;
  message.fault_reason = fault_reason;
  message.software_max_safe_temp_c = software_max_safe_temp_c;
  return message;
}

String AckBuilder::to_json(const edge::domain::ParameterAckMessage& m) const {
  String payload = "{\"device_id\":\"";
  payload += m.device_id;
  payload += "\",\"ack_type\":\"";
  payload += m.ack_type;
  payload += "\",\"success\":";
  payload += m.success ? "true" : "false";
  payload += ",\"applied_immediately\":";
  payload += m.applied_immediately ? "true" : "false";
  payload += ",\"has_pending_params\":";
  payload += m.has_pending_params ? "true" : "false";
  payload += ",\"target_temp_c\":";
  payload += String(m.runtime.target_temp_c, 2);
  payload += ",\"kp\":";
  payload += String(m.runtime.kp, 2);
  payload += ",\"ki\":";
  payload += String(m.runtime.ki, 2);
  payload += ",\"kd\":";
  payload += String(m.runtime.kd, 2);
  payload += ",\"control_period_ms\":";
  payload += String(m.runtime.control_period_ms);
  payload += ",\"control_mode\":\"";
  payload += m.runtime.control_mode;
  payload += "\",\"reason\":\"";
  payload += m.reason;
  payload += "\",\"uptime_ms\":";
  payload += String(m.uptime_ms);
  payload += ",\"sensor_valid\":";
  payload += m.sensor_valid ? "true" : "false";
  payload += ",\"fault_latched\":";
  payload += m.fault_latched ? "true" : "false";
  payload += ",\"fault_reason\":\"";
  payload += m.fault_reason;
  payload += "\"";
  payload += ",\"software_max_safe_temp_c\":";
  payload += String(m.software_max_safe_temp_c, 2);
  payload += "}";
  return payload;
}

}  // namespace edge::comms::mqtt
