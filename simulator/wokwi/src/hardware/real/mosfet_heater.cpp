#include "hardware/real/mosfet_heater.h"

namespace edge::hardware::real {

MosfetHeater::MosfetHeater(uint8_t pin, uint8_t channel, uint32_t frequency_hz,
                           uint8_t resolution_bits)
    : pin_(pin),
      channel_(channel),
      frequency_hz_(frequency_hz),
      resolution_bits_(resolution_bits) {}

void MosfetHeater::begin() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ready_ = ledcAttach(pin_, frequency_hz_, resolution_bits_);
  if (ready_) {
    ledcWrite(pin_, 0);
  }
#else
  const uint32_t configured =
      ledcSetup(channel_, frequency_hz_, resolution_bits_);
  ready_ = configured > 0;
  if (ready_) {
    ledcAttachPin(pin_, channel_);
    ledcWrite(channel_, 0);
  }
#endif
}

void MosfetHeater::write_duty(uint8_t duty) {
  if (!ready_) {
    return;
  }
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(pin_, duty);
#else
  ledcWrite(channel_, duty);
#endif
}

}  // namespace edge::hardware::real
