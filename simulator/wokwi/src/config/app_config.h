#pragma once

#include <Arduino.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

namespace edge::config {

struct ControlConfig {
  float target_temp_c = 35.0f;
  float kp = 120.0f;
  float ki = 12.0f;
  float integral_min = -20.0f;
  float integral_max = 20.0f;
  uint8_t max_duty = 255;
  uint32_t control_period_ms = 1000;
};

struct SimConfig {
  float ambient_temp_c = 22.0f;
  float initial_temp_c = 24.0f;
  float heat_gain_per_cycle_c = 1.60f;
  float cooling_factor = 0.08f;
};

struct NetworkConfig {
  const char* wifi_ssid = ProjectSecrets::kWifiSsid;
  const char* wifi_password = ProjectSecrets::kWifiPassword;
  const char* mqtt_host = ProjectSecrets::kMqttHost;
  uint16_t mqtt_port = ProjectSecrets::kMqttPort;
  const char* mqtt_username = ProjectSecrets::kMqttUsername;
  const char* mqtt_password = ProjectSecrets::kMqttPassword;
  const char* mqtt_client_id = "edge-node-001-sim";
  const char* telemetry_topic = "edge/temperature/edge-node-001/telemetry";
};

struct AppConfig {
  const char* device_id = "edge-node-001";
  bool prefer_simulated_feedback = true;
  uint32_t heartbeat_period_ms = 500;
  uint32_t main_loop_delay_ms = 20;
  ControlConfig control;
  SimConfig sim;
  NetworkConfig network;
};

inline AppConfig DefaultAppConfig() { return AppConfig{}; }

}  // namespace edge::config
