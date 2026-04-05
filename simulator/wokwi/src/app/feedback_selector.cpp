#include "app/feedback_selector.h"

namespace edge::app {

edge::domain::TemperatureSample FeedbackSelector::select(
    float sensor_temp_c, bool sensor_valid, float simulated_temp_c) const {
  if (prefer_simulated_) {
    edge::domain::TemperatureSample sample;
    sample.temperature_c = simulated_temp_c;
    sample.valid = true;
    sample.source = edge::domain::FeedbackSourceType::kSimulated;
    return sample;
  }

  if (sensor_valid) {
    edge::domain::TemperatureSample sample;
    sample.temperature_c = sensor_temp_c;
    sample.valid = true;
    sample.source = edge::domain::FeedbackSourceType::kSensor;
    return sample;
  }

  // In real-device mode, invalid sensor input must not silently fall back to
  // simulated feedback. Surface invalid sensor feedback explicitly.
  edge::domain::TemperatureSample sample;
  sample.temperature_c = sensor_temp_c;
  sample.valid = false;
  sample.source = edge::domain::FeedbackSourceType::kSensor;
  return sample;
}

}  // namespace edge::app
