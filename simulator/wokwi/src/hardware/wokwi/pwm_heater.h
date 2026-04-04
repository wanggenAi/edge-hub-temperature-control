#pragma once

#include <Arduino.h>
#include <esp_arduino_version.h>

#include "hardware/interfaces/actuator.h"

namespace edge::hardware::wokwi {

class PwmHeater final : public edge::hardware::IActuator {
 public:
  PwmHeater(uint8_t pin, uint8_t channel, uint32_t frequency_hz,
            uint8_t resolution_bits);

  void begin() override;
  void write_duty(uint8_t duty) override;

 private:
  uint8_t pin_;
  uint8_t channel_;
  uint32_t frequency_hz_;
  uint8_t resolution_bits_;
  bool ready_ = false;
};

}  // namespace edge::hardware::wokwi
