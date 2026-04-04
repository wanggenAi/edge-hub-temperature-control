#pragma once

#include <Arduino.h>

namespace edge::hardware {

class IActuator {
 public:
  virtual ~IActuator() = default;
  virtual void begin() = 0;
  virtual void write_duty(uint8_t duty) = 0;
};

}  // namespace edge::hardware
