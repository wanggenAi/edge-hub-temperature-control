#include "comms/mqtt/mqtt_gateway.h"

namespace edge::comms::mqtt {

MqttGateway::MqttGateway(const edge::config::NetworkConfig& cfg)
    : cfg_(cfg), mqtt_client_(wifi_client_) {}

void MqttGateway::begin() {
  mqtt_client_.setServer(cfg_.mqtt_host, cfg_.mqtt_port);
  mqtt_client_.setBufferSize(1024);
}

void MqttGateway::ensure_wifi(unsigned long now_ms) {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
  if (now_ms - last_wifi_attempt_ms_ < 5000) {
    return;
  }

  last_wifi_attempt_ms_ = now_ms;
  wifi_ready_printed_ = false;
  WiFi.mode(WIFI_STA);
  WiFi.begin(cfg_.wifi_ssid, cfg_.wifi_password);
}

void MqttGateway::ensure_mqtt(unsigned long now_ms) {
  if (WiFi.status() != WL_CONNECTED || mqtt_client_.connected()) {
    return;
  }
  if (now_ms - last_mqtt_attempt_ms_ < 5000) {
    return;
  }

  last_mqtt_attempt_ms_ = now_ms;
  mqtt_client_.connect(cfg_.mqtt_client_id, cfg_.mqtt_username, cfg_.mqtt_password);
}

void MqttGateway::maintain(unsigned long now_ms) {
  ensure_wifi(now_ms);

  if (WiFi.status() == WL_CONNECTED && !wifi_ready_printed_) {
    wifi_ready_printed_ = true;
    Serial.print("wifi_connected_ip=");
    Serial.println(WiFi.localIP());
  }

  ensure_mqtt(now_ms);
  if (mqtt_client_.connected()) {
    mqtt_client_.loop();
  }
}

String MqttGateway::telemetry_to_json(const edge::domain::TelemetrySnapshot& s) const {
  String payload = "{\"device_id\":\"";
  payload += s.device_id;
  payload += "\",\"uptime_ms\":";
  payload += String(s.uptime_ms);
  payload += ",\"target_temp_c\":";
  payload += String(s.target_temp_c, 2);
  payload += ",\"measured_temp_c\":";
  payload += String(s.measured_temp_c, 2);
  payload += ",\"sensor_temp_c\":";
  payload += s.sensor_valid ? String(s.sensor_temp_c, 2) : String("null");
  payload += ",\"simulated_temp_c\":";
  payload += String(s.simulated_temp_c, 2);
  payload += ",\"using_simulated_feedback\":";
  payload += s.using_simulated_feedback ? "true" : "false";
  payload += ",\"pwm_duty\":";
  payload += String(s.control.pwm_duty);
  payload += ",\"pwm_norm\":";
  payload += String(s.control.pwm_norm, 3);
  payload += ",\"error_c\":";
  payload += String(s.control.error_c, 2);
  payload += ",\"integral_error\":";
  payload += String(s.control.integral_error, 2);
  payload += "}";
  return payload;
}

bool MqttGateway::publish_telemetry(const edge::domain::TelemetrySnapshot& snapshot) {
  if (!mqtt_client_.connected()) {
    return false;
  }
  const String payload = telemetry_to_json(snapshot);
  return mqtt_client_.publish(cfg_.telemetry_topic, payload.c_str());
}

}  // namespace edge::comms::mqtt
