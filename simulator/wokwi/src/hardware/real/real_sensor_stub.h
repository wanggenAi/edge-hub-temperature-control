#pragma once

#include "hardware/interfaces/temperature_sensor.h"

namespace edge::hardware::real {

class RealSensorStub final : public edge::hardware::ITemperatureSensor {
 public:
  void begin() override {}
  float read_celsius() override { return 0.0f; }
  bool is_valid(float value_c) const override { return value_c > -1000.0f; }
};

}  // namespace edge::hardware::real
