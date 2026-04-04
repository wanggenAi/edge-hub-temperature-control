#pragma once

#include "domain/model/control_types.h"

namespace edge::app {

class FeedbackSelector {
 public:
  explicit FeedbackSelector(bool prefer_simulated)
      : prefer_simulated_(prefer_simulated) {}

  edge::domain::TemperatureSample select(float sensor_temp_c,
                                         bool sensor_valid,
                                         float simulated_temp_c) const;

 private:
  bool prefer_simulated_ = true;
};

}  // namespace edge::app
