#pragma once

namespace edge::hardware {

class ITemperatureSensor {
 public:
  virtual ~ITemperatureSensor() = default;
  virtual void begin() = 0;
  virtual float read_celsius() = 0;
  virtual bool is_valid(float value_c) const = 0;
};

}  // namespace edge::hardware
