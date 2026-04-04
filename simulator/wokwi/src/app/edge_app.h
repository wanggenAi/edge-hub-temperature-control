#pragma once

#include "app/feedback_selector.h"
#include "app/migration_hooks.h"
#include "comms/mqtt/mqtt_gateway.h"
#include "config/app_config.h"
#include "config/build_profile.h"
#include "controller/pi_controller.h"
#include "domain/model/runtime_state.h"
#include "hardware/interfaces/actuator.h"
#include "hardware/interfaces/temperature_sensor.h"
#include "hardware/wokwi/thermal_plant_model.h"

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
  void run_control_tick(unsigned long now_ms);
  void update_heartbeat(unsigned long now_ms);
  edge::domain::TelemetrySnapshot build_snapshot(
      unsigned long now_ms,
      const edge::domain::TemperatureSample& feedback,
      const edge::domain::ControllerOutput& control) const;

  edge::config::AppConfig cfg_;
  edge::hardware::ITemperatureSensor& sensor_;
  edge::hardware::IActuator& actuator_;
  edge::comms::mqtt::MqttGateway& mqtt_;

  FeedbackSelector feedback_selector_;
  edge::controller::PiController controller_;
  edge::hardware::wokwi::ThermalPlantModel plant_model_;
  MigrationHooks hooks_;

  edge::domain::RuntimeState state_;
};

}  // namespace edge::app
