#include "hardware/real/real_ds18b20_sensor.h"

namespace edge::hardware::real {

RealDs18b20Sensor::RealDs18b20Sensor(uint8_t pin)
    : one_wire_(pin), sensors_(&one_wire_) {}

void RealDs18b20Sensor::begin() {
  sensors_.begin();
  sensors_.setResolution(12);
}

float RealDs18b20Sensor::read_celsius() {
  sensors_.requestTemperatures();
  return sensors_.getTempCByIndex(0);
}

bool RealDs18b20Sensor::is_valid(float value_c) const {
  return value_c != DEVICE_DISCONNECTED_C;
}

}  // namespace edge::hardware::real
