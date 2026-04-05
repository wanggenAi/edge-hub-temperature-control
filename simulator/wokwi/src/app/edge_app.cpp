#include "app/edge_app.h"

#include <Arduino.h>
#include <esp_system.h>
#include <string.h>

#include "config/pins.h"

namespace edge::app {

namespace {

edge::comms::mqtt::ParamUpdateHandler::Dependencies BuildParamDeps(
    const char* device_id,
    edge::app::RuntimeConfigStore* store,
    const edge::comms::mqtt::ParamMessageParser* parser,
    const edge::comms::mqtt::ParamValidator* validator,
    const edge::comms::mqtt::AckBuilder* ack_builder,
    bool (*publish_ack)(const String&, void*),
    void* publish_ack_ctx,
    void (*on_runtime_applied)(bool, void*),
    void* on_runtime_applied_ctx,
    void (*enrich_ack)(edge::domain::ParameterAckMessage*, void*),
    void* enrich_ack_ctx) {
  edge::comms::mqtt::ParamUpdateHandler::Dependencies deps{};
  deps.device_id = device_id;
  deps.store = store;
  deps.parser = parser;
  deps.validator = validator;
  deps.ack_builder = ack_builder;
  deps.publish_ack = publish_ack;
  deps.publish_ack_ctx = publish_ack_ctx;
  deps.on_runtime_applied = on_runtime_applied;
  deps.on_runtime_applied_ctx = on_runtime_applied_ctx;
  deps.enrich_ack = enrich_ack;
  deps.enrich_ack_ctx = enrich_ack_ctx;
  return deps;
}

}  // namespace

edge::domain::RuntimeControlConfig EdgeTemperatureApp::build_initial_runtime_config(
    const edge::config::AppConfig& config) const {
  edge::domain::RuntimeControlConfig runtime;
  runtime.target_temp_c = config.control.target_temp_c;
  runtime.kp = config.control.kp;
  runtime.ki = config.control.ki;
  runtime.kd = config.control.kd;
  runtime.control_period_ms = config.control.control_period_ms;
  strncpy(runtime.control_mode, config.default_control_mode,
          sizeof(runtime.control_mode) - 1);
  runtime.control_mode[sizeof(runtime.control_mode) - 1] = '\0';
  return runtime;
}

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
#if EDGE_BUILD_SIMULATOR
      plant_model_(config.sim),
#endif
      hooks_(hooks),
      runtime_store_(build_initial_runtime_config(config)),
      param_validator_(config.control),
      param_handler_(BuildParamDeps(config.device_id, &runtime_store_, &param_parser_,
                                    &param_validator_, &ack_builder_,
                                    publish_ack_adapter, this,
                                    on_runtime_applied_adapter, this,
                                    enrich_ack_adapter, this)) {
  state_.simulated_temp_c = config.sim.initial_temp_c;
  snprintf(run_id_, sizeof(run_id_), "%s-run-%08lx", config.device_id,
           static_cast<unsigned long>(esp_random()));
}

void EdgeTemperatureApp::setup() {
  Serial.begin(115200);
  delay(150);

  pinMode(edge::config::pins::kStatusLed, OUTPUT);
  digitalWrite(edge::config::pins::kStatusLed, LOW);

  sensor_.begin();
  actuator_.begin();
  mqtt_.begin();
  mqtt_.set_params_message_callback(on_mqtt_params_adapter, this);

  state_.last_control_ms = millis() - runtime_store_.current().control_period_ms;
  state_.last_heartbeat_ms = millis();

  Serial.println("edge_temperature_app_boot=ok");
  Serial.print("feedback_prefer_simulated=");
  Serial.println(cfg_.prefer_simulated_feedback ? "true" : "false");
  Serial.print("run_id=");
  Serial.println(run_id_);
  Serial.print("mqtt_telemetry_topic=");
  Serial.println(cfg_.network.telemetry_topic);
  Serial.print("mqtt_params_topic=");
  Serial.println(cfg_.network.params_set_topic);
  Serial.print("mqtt_params_ack_topic=");
  Serial.println(cfg_.network.params_ack_topic);
  print_runtime_config_snapshot();
}

void EdgeTemperatureApp::loop_once() {
  const unsigned long now_ms = millis();
  mqtt_.maintain(now_ms);
  update_heartbeat(now_ms);
  run_control_tick(now_ms);
  delay(cfg_.main_loop_delay_ms);
}

void EdgeTemperatureApp::on_mqtt_params_adapter(const String& payload,
                                                unsigned long now_ms,
                                                void* ctx) {
  if (ctx == nullptr) {
    return;
  }
  auto* app = static_cast<EdgeTemperatureApp*>(ctx);
  app->param_handler_.on_params_message(payload, now_ms);
}

bool EdgeTemperatureApp::publish_ack_adapter(const String& payload, void* ctx) {
  if (ctx == nullptr) {
    return false;
  }
  auto* app = static_cast<EdgeTemperatureApp*>(ctx);
  return app->mqtt_.publish_ack_json(payload);
}

void EdgeTemperatureApp::on_runtime_applied_adapter(bool reset_integral, void* ctx) {
  if (ctx == nullptr) {
    return;
  }
  auto* app = static_cast<EdgeTemperatureApp*>(ctx);
  app->on_runtime_applied(reset_integral);
}

void EdgeTemperatureApp::enrich_ack_adapter(edge::domain::ParameterAckMessage* message,
                                            void* ctx) {
  if (ctx == nullptr || message == nullptr) {
    return;
  }
  auto* app = static_cast<EdgeTemperatureApp*>(ctx);
  app->enrich_ack(message);
}

void EdgeTemperatureApp::enrich_ack(edge::domain::ParameterAckMessage* message) const {
  if (message == nullptr) {
    return;
  }
  message->sensor_valid = state_.sensor_valid;
  message->fault_latched = state_.fault_latched;
  message->fault_reason = state_.fault_reason;
  message->software_max_safe_temp_c = cfg_.control.software_max_safe_temp_c;
}

void EdgeTemperatureApp::latch_fault(const char* reason) {
  if (state_.fault_latched) {
    return;
  }
  state_.fault_latched = true;
  strncpy(state_.fault_reason, reason, sizeof(state_.fault_reason) - 1);
  state_.fault_reason[sizeof(state_.fault_reason) - 1] = '\0';
  controller_.reset_integral();
  actuator_.write_duty(0);
  Serial.print("safety_fault_latched=");
  Serial.println(state_.fault_reason);
}

void EdgeTemperatureApp::clear_fault_if_possible() {
  if (!state_.fault_latched) {
    return;
  }
  if (cfg_.control.fault_latch_enabled) {
    return;
  }
  if (!state_.sensor_valid) {
    return;
  }
  if (state_.sensor_temp_c > cfg_.control.software_max_safe_temp_c - 2.0f) {
    return;
  }
  state_.fault_latched = false;
  strncpy(state_.fault_reason, "none", sizeof(state_.fault_reason) - 1);
  state_.fault_reason[sizeof(state_.fault_reason) - 1] = '\0';
}

void EdgeTemperatureApp::on_runtime_applied(bool reset_integral) {
  if (reset_integral) {
    controller_.reset_integral();
  }
  print_runtime_config_snapshot();
}

void EdgeTemperatureApp::run_control_tick(unsigned long now_ms) {
  const edge::domain::RuntimeControlConfig runtime = runtime_store_.current();
  const unsigned long elapsed_ms = now_ms - state_.last_control_ms;
  if (elapsed_ms < runtime.control_period_ms) {
    return;
  }
  state_.last_control_ms = now_ms;
  state_.last_actual_dt_ms = elapsed_ms;
  state_.last_dt_error_ms =
      static_cast<long>(elapsed_ms) - static_cast<long>(runtime.control_period_ms);

  param_handler_.apply_pending_if_needed(now_ms);

  if (hooks_.before_control_tick != nullptr) {
    hooks_.before_control_tick();
  }

  const float sensor_temp = sensor_.read_celsius();
  state_.sensor_valid = sensor_.is_valid(sensor_temp);
  state_.sensor_temp_c = sensor_temp;

  if (!state_.sensor_valid) {
    latch_fault("sensor_invalid");
  } else if (state_.sensor_temp_c > cfg_.control.software_max_safe_temp_c) {
    latch_fault("software_overtemp");
  }
  clear_fault_if_possible();

  const edge::domain::TemperatureSample feedback =
      feedback_selector_.select(state_.sensor_temp_c, state_.sensor_valid,
                                state_.simulated_temp_c);

  edge::domain::ControllerInput input;
  input.target_temp_c = runtime_store_.current().target_temp_c;
  input.measured_temp_c = feedback.temperature_c;
  input.dt_s = static_cast<float>(elapsed_ms) / 1000.0f;
  if (input.dt_s <= 0.0f) {
    input.dt_s = runtime_store_.current().control_period_ms / 1000.0f;
  }

  bool safety_output_forced_off = state_.fault_latched;
  edge::domain::ControllerOutput control{};
  if (safety_output_forced_off) {
    control.error_c = input.target_temp_c - input.measured_temp_c;
    control.control_output = 0.0f;
    control.pwm_duty = 0;
    control.pwm_norm = 0.0f;
    control.saturation_state = edge::domain::SaturationState::kLow;
    actuator_.write_duty(0);
  } else {
    control = controller_.update(input, runtime_store_.current());
    actuator_.write_duty(control.pwm_duty);
  }

#if EDGE_BUILD_SIMULATOR
  state_.simulated_temp_c =
      plant_model_.step(state_.simulated_temp_c, control.pwm_norm);
#endif

  const edge::domain::TelemetrySnapshot snapshot =
      build_snapshot(now_ms, feedback, control, safety_output_forced_off);

  const String telemetry_json = telemetry_builder_.to_json(snapshot);
  Serial.println(telemetry_json);
  mqtt_.publish_telemetry(snapshot);

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

void EdgeTemperatureApp::print_runtime_config_snapshot() const {
  const edge::domain::RuntimeControlConfig runtime = runtime_store_.current();
  Serial.print("runtime_target_temp_c=");
  Serial.println(runtime.target_temp_c, 2);
  Serial.print("runtime_kp=");
  Serial.println(runtime.kp, 2);
  Serial.print("runtime_ki=");
  Serial.println(runtime.ki, 2);
  Serial.print("runtime_kd=");
  Serial.println(runtime.kd, 2);
  Serial.print("runtime_control_period_ms=");
  Serial.println(runtime.control_period_ms);
  Serial.print("runtime_control_mode=");
  Serial.println(runtime.control_mode);
}

edge::domain::TelemetrySnapshot EdgeTemperatureApp::build_snapshot(
    unsigned long now_ms,
    const edge::domain::TemperatureSample& feedback,
    const edge::domain::ControllerOutput& control,
    bool safety_output_forced_off) const {
  const auto net_stats = mqtt_.network_stats();
  edge::domain::TelemetrySnapshot snapshot{};
  snapshot.device_id = cfg_.device_id;
  snapshot.uptime_ms = now_ms;
  snapshot.target_temp_c = runtime_store_.current().target_temp_c;
  snapshot.measured_temp_c = feedback.temperature_c;
  snapshot.sensor_temp_c = state_.sensor_temp_c;
  snapshot.simulated_temp_c = state_.simulated_temp_c;
  snapshot.sensor_valid = state_.sensor_valid;
  snapshot.sensor_status = state_.sensor_valid ? "ok" : "invalid";
  snapshot.using_simulated_feedback =
      feedback.source == edge::domain::FeedbackSourceType::kSimulated;
  snapshot.control_period_ms = runtime_store_.current().control_period_ms;
  snapshot.actual_dt_ms = state_.last_actual_dt_ms;
  snapshot.dt_error_ms = state_.last_dt_error_ms;
  snapshot.wifi_connected = net_stats.wifi_connected;
  snapshot.mqtt_connected = net_stats.mqtt_connected;
  snapshot.mqtt_reconnect_count = net_stats.mqtt_reconnect_count;
  snapshot.mqtt_publish_fail_count = net_stats.mqtt_publish_fail_count;
  snapshot.run_id = run_id_;
  snapshot.control_mode = runtime_store_.current().control_mode;
  snapshot.controller_version = cfg_.controller_version;
  snapshot.kp = runtime_store_.current().kp;
  snapshot.ki = runtime_store_.current().ki;
  snapshot.kd = runtime_store_.current().kd;
  snapshot.system_state = cfg_.system_state;
  snapshot.safety_output_forced_off = safety_output_forced_off;
  snapshot.fault_latched = state_.fault_latched;
  snapshot.fault_reason = state_.fault_reason;
  snapshot.software_max_safe_temp_c = cfg_.control.software_max_safe_temp_c;
  snapshot.has_pending_params = runtime_store_.has_pending();
  snapshot.pending_params_age_ms = runtime_store_.pending_age_ms(now_ms);
  snapshot.control = control;
  return snapshot;
}

}  // namespace edge::app
