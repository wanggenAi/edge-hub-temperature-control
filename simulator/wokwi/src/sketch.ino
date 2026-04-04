#include "app/edge_app.h"
#include "comms/mqtt/mqtt_gateway.h"
#include "config/app_config.h"
#include "config/build_profile.h"
#include "config/pins.h"

#if EDGE_BUILD_SIMULATOR
#include "hardware/wokwi/ds18b20_sensor.h"
#include "hardware/wokwi/pwm_heater.h"
#else
#include "hardware/real/mosfet_heater.h"
#include "hardware/real/real_ds18b20_sensor.h"
#endif

namespace {

edge::config::AppConfig BuildConfig() {
  edge::config::AppConfig config = edge::config::DefaultAppConfig();
#if EDGE_BUILD_SIMULATOR
  config.prefer_simulated_feedback = true;
#else
  config.prefer_simulated_feedback = false;
#endif
  return config;
}

edge::config::AppConfig g_config = BuildConfig();

#if EDGE_BUILD_SIMULATOR
edge::hardware::wokwi::Ds18b20Sensor g_sensor(edge::config::pins::kOneWireBus);
edge::hardware::wokwi::PwmHeater g_actuator(
#else
edge::hardware::real::RealDs18b20Sensor g_sensor(edge::config::pins::kOneWireBus);
edge::hardware::real::MosfetHeater g_actuator(
#endif
    edge::config::pins::kPwmOutput,
    edge::config::pins::kPwmChannel,
    5000,
    8);
edge::comms::mqtt::MqttGateway g_mqtt(g_config.network);
edge::app::EdgeTemperatureApp g_app(g_config, g_sensor, g_actuator, g_mqtt);

}  // namespace

void setup() { g_app.setup(); }

void loop() { g_app.loop_once(); }
