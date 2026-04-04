#pragma once

#include "hardware/interfaces/actuator.h"

namespace edge::hardware::real {

class RealActuatorStub final : public edge::hardware::IActuator {
 public:
  void begin() override {}
  void write_duty(uint8_t duty) override { (void)duty; }
};

}  // namespace edge::hardware::real
