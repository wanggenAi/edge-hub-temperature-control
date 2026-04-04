#pragma once

#include <PubSubClient.h>
#include <WiFi.h>

#include "config/app_config.h"
#include "domain/model/control_types.h"

namespace edge::comms::mqtt {

class MqttGateway {
 public:
  explicit MqttGateway(const edge::config::NetworkConfig& cfg);

  void begin();
  void maintain(unsigned long now_ms);
  bool publish_telemetry(const edge::domain::TelemetrySnapshot& snapshot);

 private:
  String telemetry_to_json(const edge::domain::TelemetrySnapshot& snapshot) const;
  void ensure_wifi(unsigned long now_ms);
  void ensure_mqtt(unsigned long now_ms);

  edge::config::NetworkConfig cfg_;
  WiFiClient wifi_client_;
  PubSubClient mqtt_client_;

  unsigned long last_wifi_attempt_ms_ = 0;
  unsigned long last_mqtt_attempt_ms_ = 0;
  bool wifi_ready_printed_ = false;
};

}  // namespace edge::comms::mqtt
