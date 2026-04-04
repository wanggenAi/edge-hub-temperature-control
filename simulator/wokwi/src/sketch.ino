#include "app/edge_app.h"
#include "comms/mqtt/mqtt_gateway.h"
#include "config/app_config.h"
#include "config/pins.h"
#include "hardware/wokwi/ds18b20_sensor.h"
#include "hardware/wokwi/pwm_heater.h"

namespace {

edge::config::AppConfig g_config = edge::config::DefaultAppConfig();
edge::hardware::wokwi::Ds18b20Sensor g_sensor(edge::config::pins::kOneWireBus);
edge::hardware::wokwi::PwmHeater g_actuator(
    edge::config::pins::kPwmOutput,
    edge::config::pins::kPwmChannel,
    5000,
    8);
edge::comms::mqtt::MqttGateway g_mqtt(g_config.network);
edge::app::EdgeTemperatureApp g_app(g_config, g_sensor, g_actuator, g_mqtt);

}  // namespace

void setup() { g_app.setup(); }

void loop() { g_app.loop_once(); }
