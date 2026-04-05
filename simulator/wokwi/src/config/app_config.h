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
  float kd = 0.0f;
  float integral_min = -20.0f;
  float integral_max = 20.0f;
  uint8_t max_duty = 255;
  uint32_t control_period_ms = 1000;
  float min_target_temp_c = 20.0f;
  float max_target_temp_c = 60.0f;
  float min_gain = 0.0f;
  float max_gain = 1000.0f;
  uint32_t min_control_period_ms = 200;
  uint32_t max_control_period_ms = 10000;
  float software_max_safe_temp_c = 65.0f;
  bool fault_latch_enabled = true;
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
  const char* params_set_topic = "edge/temperature/edge-node-001/params/set";
  const char* params_ack_topic = "edge/temperature/edge-node-001/params/ack";
  uint16_t mqtt_client_buffer_size = 1024;
  uint32_t wifi_reconnect_interval_ms = 5000;
  uint32_t mqtt_reconnect_interval_ms = 5000;
};

struct AppConfig {
  const char* device_id = "edge-node-001";
  const char* controller_version = "pi_tuned_v3_1";
  const char* system_state = "running";
  const char* default_control_mode = "pid_control";
  uint8_t text_field_size = 32;
  uint8_t run_id_size = 48;
  bool prefer_simulated_feedback = true;
  uint32_t heartbeat_period_ms = 500;
  uint32_t main_loop_delay_ms = 20;
  ControlConfig control;
  SimConfig sim;
  NetworkConfig network;
};

inline AppConfig DefaultAppConfig() { return AppConfig{}; }

}  // namespace edge::config
