#pragma once

#include <PubSubClient.h>
#include <WiFi.h>

#include "config/app_config.h"
#include "comms/mqtt/telemetry_builder.h"
#include "domain/model/control_types.h"

namespace edge::comms::mqtt {

class MqttGateway {
 public:
  using ParamsMessageCallback =
      void (*)(const String& payload, unsigned long now_ms, void* ctx);

  explicit MqttGateway(const edge::config::NetworkConfig& cfg);

  void begin();
  void maintain(unsigned long now_ms);
  void set_params_message_callback(ParamsMessageCallback callback, void* ctx);
  bool publish_telemetry(const edge::domain::TelemetrySnapshot& snapshot);
  bool publish_ack_json(const String& payload);
  bool connected();

 private:
  static void mqtt_callback_router(char* topic, byte* payload, unsigned int length);
  void handle_mqtt_message(char* topic, byte* payload, unsigned int length);
  void ensure_wifi(unsigned long now_ms);
  void ensure_mqtt(unsigned long now_ms);

  static MqttGateway* active_instance_;

  edge::config::NetworkConfig cfg_;
  WiFiClient wifi_client_;
  PubSubClient mqtt_client_;
  TelemetryBuilder telemetry_builder_;
  ParamsMessageCallback params_callback_ = nullptr;
  void* params_callback_ctx_ = nullptr;

  unsigned long last_wifi_attempt_ms_ = 0;
  unsigned long last_mqtt_attempt_ms_ = 0;
  bool wifi_ready_printed_ = false;
};

}  // namespace edge::comms::mqtt
