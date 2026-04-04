#include "hardware/wokwi/thermal_plant_model.h"

namespace edge::hardware::wokwi {

float ThermalPlantModel::step(float current_temp_c, float normalized_duty) const {
  const float heating = cfg_.heat_gain_per_cycle_c * normalized_duty;
  const float cooling = cfg_.cooling_factor * (current_temp_c - cfg_.ambient_temp_c);
  return current_temp_c + heating - cooling;
}

}  // namespace edge::hardware::wokwi
