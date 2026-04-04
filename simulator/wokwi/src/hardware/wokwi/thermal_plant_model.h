#pragma once

#include "config/app_config.h"

namespace edge::hardware::wokwi {

class ThermalPlantModel {
 public:
  explicit ThermalPlantModel(const edge::config::SimConfig& config)
      : cfg_(config) {}

  float step(float current_temp_c, float normalized_duty) const;

 private:
  edge::config::SimConfig cfg_;
};

}  // namespace edge::hardware::wokwi
