#pragma once

#include "app/feedback_selector.h"
#include "app/migration_hooks.h"
#include "app/runtime_config_store.h"
#include "comms/mqtt/ack_builder.h"
#include "comms/mqtt/mqtt_gateway.h"
#include "comms/mqtt/param_message_parser.h"
#include "comms/mqtt/param_update_handler.h"
#include "comms/mqtt/param_validator.h"
#include "comms/mqtt/telemetry_builder.h"
#include "config/app_config.h"
#include "config/build_profile.h"
#include "controller/pi_controller.h"
#include "domain/model/runtime_state.h"
#include "hardware/interfaces/actuator.h"
#include "hardware/interfaces/temperature_sensor.h"
#if EDGE_BUILD_SIMULATOR
#include "hardware/wokwi/thermal_plant_model.h"
#endif

namespace edge::app {

class EdgeTemperatureApp {
 public:
  EdgeTemperatureApp(const edge::config::AppConfig& config,
                     edge::hardware::ITemperatureSensor& sensor,
                     edge::hardware::IActuator& actuator,
                     edge::comms::mqtt::MqttGateway& mqtt,
                     const MigrationHooks& hooks = {});

  void setup();
  void loop_once();

 private:
  static void on_mqtt_params_adapter(const String& payload,
                                     unsigned long now_ms,
                                     void* ctx);
  static bool publish_ack_adapter(const String& payload, void* ctx);
  static void on_runtime_applied_adapter(bool reset_integral, void* ctx);
  static void enrich_ack_adapter(edge::domain::ParameterAckMessage* message, void* ctx);

  void run_control_tick(unsigned long now_ms);
  void update_heartbeat(unsigned long now_ms);
  void print_runtime_config_snapshot() const;
  void on_runtime_applied(bool reset_integral);
  void enrich_ack(edge::domain::ParameterAckMessage* message) const;
  void latch_fault(const char* reason);
  void clear_fault_if_possible();
  edge::domain::TelemetrySnapshot build_snapshot(
      unsigned long now_ms,
      const edge::domain::TemperatureSample& feedback,
      const edge::domain::ControllerOutput& control,
      bool safety_output_forced_off) const;
  edge::domain::RuntimeControlConfig build_initial_runtime_config(
      const edge::config::AppConfig& config) const;

  edge::config::AppConfig cfg_;
  edge::hardware::ITemperatureSensor& sensor_;
  edge::hardware::IActuator& actuator_;
  edge::comms::mqtt::MqttGateway& mqtt_;

  FeedbackSelector feedback_selector_;
  edge::controller::PiController controller_;
#if EDGE_BUILD_SIMULATOR
  edge::hardware::wokwi::ThermalPlantModel plant_model_;
#endif
  MigrationHooks hooks_;
  RuntimeConfigStore runtime_store_;
  edge::comms::mqtt::ParamMessageParser param_parser_;
  edge::comms::mqtt::ParamValidator param_validator_;
  edge::comms::mqtt::AckBuilder ack_builder_;
  edge::comms::mqtt::ParamUpdateHandler param_handler_;
  edge::comms::mqtt::TelemetryBuilder telemetry_builder_;
  char run_id_[64] = {};

  edge::domain::RuntimeState state_;
};

}  // namespace edge::app
