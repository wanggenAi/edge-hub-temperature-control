#pragma once

#include <DallasTemperature.h>
#include <OneWire.h>

#include "hardware/interfaces/temperature_sensor.h"

namespace edge::hardware::wokwi {

class Ds18b20Sensor final : public edge::hardware::ITemperatureSensor {
 public:
  explicit Ds18b20Sensor(uint8_t pin);

  void begin() override;
  float read_celsius() override;
  bool is_valid(float value_c) const override;

 private:
  OneWire one_wire_;
  DallasTemperature sensors_;
};

}  // namespace edge::hardware::wokwi
