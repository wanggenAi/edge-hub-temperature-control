#include "app/edge_app.h"

#include <Arduino.h>

#include "config/pins.h"
#include "domain/model/control_types.h"

namespace edge::app {

EdgeTemperatureApp::EdgeTemperatureApp(const edge::config::AppConfig& config,
                                       edge::hardware::ITemperatureSensor& sensor,
                                       edge::hardware::IActuator& actuator,
                                       edge::comms::mqtt::MqttGateway& mqtt,
                                       const MigrationHooks& hooks)
    : cfg_(config),
      sensor_(sensor),
      actuator_(actuator),
      mqtt_(mqtt),
      feedback_selector_(config.prefer_simulated_feedback),
      controller_(config.control),
      plant_model_(config.sim),
      hooks_(hooks) {
  state_.simulated_temp_c = config.sim.initial_temp_c;
}

void EdgeTemperatureApp::setup() {
  Serial.begin(115200);
  delay(150);

  pinMode(edge::config::pins::kStatusLed, OUTPUT);
  digitalWrite(edge::config::pins::kStatusLed, LOW);

  sensor_.begin();
  actuator_.begin();
  mqtt_.begin();

  state_.last_control_ms = millis() - cfg_.control.control_period_ms;
  state_.last_heartbeat_ms = millis();

  Serial.println("edge_temperature_app_boot=ok");
  Serial.print("feedback_prefer_simulated=");
  Serial.println(cfg_.prefer_simulated_feedback ? "true" : "false");
}

void EdgeTemperatureApp::loop_once() {
  const unsigned long now_ms = millis();
  mqtt_.maintain(now_ms);
  update_heartbeat(now_ms);
  run_control_tick(now_ms);
  delay(cfg_.main_loop_delay_ms);
}

void EdgeTemperatureApp::run_control_tick(unsigned long now_ms) {
  if (now_ms - state_.last_control_ms < cfg_.control.control_period_ms) {
    return;
  }
  state_.last_control_ms = now_ms;

  if (hooks_.before_control_tick != nullptr) {
    hooks_.before_control_tick();
  }

  const float sensor_temp = sensor_.read_celsius();
  state_.sensor_valid = sensor_.is_valid(sensor_temp);
  state_.sensor_temp_c = sensor_temp;

  const edge::domain::TemperatureSample feedback =
      feedback_selector_.select(state_.sensor_temp_c, state_.sensor_valid,
                                state_.simulated_temp_c);

  edge::domain::ControllerInput input;
  input.target_temp_c = cfg_.control.target_temp_c;
  input.measured_temp_c = feedback.temperature_c;
  input.dt_s = cfg_.control.control_period_ms / 1000.0f;

  const edge::domain::ControllerOutput control = controller_.update(input);
  actuator_.write_duty(control.pwm_duty);

#if EDGE_BUILD_SIMULATOR
  state_.simulated_temp_c =
      plant_model_.step(state_.simulated_temp_c, control.pwm_norm);
#endif

  const edge::domain::TelemetrySnapshot snapshot =
      build_snapshot(now_ms, feedback, control);

  mqtt_.publish_telemetry(snapshot);
  Serial.print("telemetry_temp_c=");
  Serial.print(snapshot.measured_temp_c, 2);
  Serial.print(", pwm_duty=");
  Serial.println(snapshot.control.pwm_duty);

  if (hooks_.after_control_tick != nullptr) {
    hooks_.after_control_tick();
  }
}

void EdgeTemperatureApp::update_heartbeat(unsigned long now_ms) {
  if (now_ms - state_.last_heartbeat_ms < cfg_.heartbeat_period_ms) {
    return;
  }
  state_.last_heartbeat_ms = now_ms;
  state_.heartbeat_state = !state_.heartbeat_state;
  digitalWrite(edge::config::pins::kStatusLed, state_.heartbeat_state ? HIGH : LOW);
}

edge::domain::TelemetrySnapshot EdgeTemperatureApp::build_snapshot(
    unsigned long now_ms,
    const edge::domain::TemperatureSample& feedback,
    const edge::domain::ControllerOutput& control) const {
  edge::domain::TelemetrySnapshot snapshot{};
  snapshot.device_id = cfg_.device_id;
  snapshot.uptime_ms = now_ms;
  snapshot.target_temp_c = cfg_.control.target_temp_c;
  snapshot.measured_temp_c = feedback.temperature_c;
  snapshot.sensor_temp_c = state_.sensor_temp_c;
  snapshot.simulated_temp_c = state_.simulated_temp_c;
  snapshot.sensor_valid = state_.sensor_valid;
  snapshot.using_simulated_feedback =
      feedback.source == edge::domain::FeedbackSourceType::kSimulated;
  snapshot.control = control;
  return snapshot;
}

}  // namespace edge::app
