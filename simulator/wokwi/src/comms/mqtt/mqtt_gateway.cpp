#include "comms/mqtt/mqtt_gateway.h"

#include <cstring>

namespace edge::comms::mqtt {

MqttGateway* MqttGateway::active_instance_ = nullptr;

MqttGateway::MqttGateway(const edge::config::NetworkConfig& cfg)
    : cfg_(cfg), mqtt_client_(cfg.mqtt_client_buffer_size) {}

void MqttGateway::begin() {
  mqtt_client_.begin(cfg_.mqtt_host, cfg_.mqtt_port, wifi_client_);
  active_instance_ = this;
  mqtt_client_.onMessageAdvanced(mqtt_callback_router);
}

void MqttGateway::set_params_message_callback(ParamsMessageCallback callback,
                                              void* ctx) {
  params_callback_ = callback;
  params_callback_ctx_ = ctx;
}

void MqttGateway::mqtt_callback_router(MQTTClient* client, char* topic, char* payload, int length) {
  (void)client;
  if (active_instance_ == nullptr) {
    return;
  }
  active_instance_->handle_mqtt_message(topic, payload, length);
}

void MqttGateway::handle_mqtt_message(char* topic, char* payload, int length) {
  if (params_callback_ == nullptr) {
    return;
  }

  if (String(topic) != cfg_.params_set_topic) {
    return;
  }

  String payload_text;
  payload_text.reserve(length);
  for (int index = 0; index < length; ++index) {
    payload_text += static_cast<char>(payload[index]);
  }

  Serial.print("mqtt_rx_topic=");
  Serial.println(topic);
  Serial.print("mqtt_rx_payload=");
  Serial.println(payload_text);

  params_callback_(payload_text, millis(), params_callback_ctx_);
}

void MqttGateway::ensure_wifi(unsigned long now_ms) {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
  if (now_ms - last_wifi_attempt_ms_ < cfg_.wifi_reconnect_interval_ms) {
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
  if (now_ms - last_mqtt_attempt_ms_ < cfg_.mqtt_reconnect_interval_ms) {
    return;
  }

  last_mqtt_attempt_ms_ = now_ms;
  const bool has_username = cfg_.mqtt_username != nullptr && std::strlen(cfg_.mqtt_username) > 0;
  const bool connected = has_username
      ? mqtt_client_.connect(cfg_.mqtt_client_id, cfg_.mqtt_username, cfg_.mqtt_password)
      : mqtt_client_.connect(cfg_.mqtt_client_id);
  if (!connected) {
    Serial.print("mqtt_connect_failed_last_error=");
    Serial.println(mqtt_client_.lastError());
    return;
  }

  Serial.println("mqtt_status=connected");
  ++mqtt_reconnect_count_;
  if (mqtt_client_.subscribe(cfg_.params_set_topic, cfg_.mqtt_qos)) {
    Serial.print("mqtt_subscribed_topic=");
    Serial.println(cfg_.params_set_topic);
  } else {
    Serial.print("mqtt_subscribe_failed_topic=");
    Serial.println(cfg_.params_set_topic);
  }
}

void MqttGateway::maintain(unsigned long now_ms) {
  ensure_wifi(now_ms);

  if (WiFi.status() == WL_CONNECTED && !wifi_ready_printed_) {
    wifi_ready_printed_ = true;
    Serial.print("wifi_connected_ip=");
    Serial.println(WiFi.localIP());
  }

  ensure_mqtt(now_ms);
  mqtt_connected_cached_ = mqtt_client_.connected();
  if (mqtt_client_.connected()) {
    mqtt_client_.loop();
  }
}

bool MqttGateway::publish_telemetry(const edge::domain::TelemetrySnapshot& snapshot) {
  if (!mqtt_client_.connected()) {
    Serial.println("mqtt_publish_skipped=not_connected");
    ++mqtt_publish_fail_count_;
    return false;
  }
  const String payload = telemetry_builder_.to_json(snapshot);
  const bool published =
      mqtt_client_.publish(cfg_.telemetry_topic, payload, false, cfg_.mqtt_qos);
  if (!published) {
    ++mqtt_publish_fail_count_;
  }
  Serial.print("mqtt_publish_status=");
  Serial.println(published ? "published" : "failed");
  return published;
}

bool MqttGateway::publish_ack_json(const String& payload) {
  Serial.print("mqtt_ack_topic=");
  Serial.println(cfg_.params_ack_topic);
  Serial.print("mqtt_ack_payload=");
  Serial.println(payload);

  if (!mqtt_client_.connected()) {
    Serial.println("mqtt_ack_status=skipped_not_connected");
    ++mqtt_publish_fail_count_;
    return false;
  }

  const bool published =
      mqtt_client_.publish(cfg_.params_ack_topic, payload, false, cfg_.mqtt_qos);
  if (!published) {
    ++mqtt_publish_fail_count_;
  }
  Serial.print("mqtt_ack_status=");
  Serial.println(published ? "published" : "failed");
  return published;
}

bool MqttGateway::connected() { return mqtt_client_.connected(); }

MqttGateway::NetworkStats MqttGateway::network_stats() const {
  NetworkStats stats{};
  stats.wifi_connected = WiFi.status() == WL_CONNECTED;
  stats.mqtt_connected = mqtt_connected_cached_;
  stats.mqtt_reconnect_count = mqtt_reconnect_count_;
  stats.mqtt_publish_fail_count = mqtt_publish_fail_count_;
  return stats;
}

}  // namespace edge::comms::mqtt
