#pragma once

#include "domain/model/control_types.h"

namespace edge::comms::mqtt {

class TelemetryBuilder {
 public:
  const char* saturation_to_text(edge::domain::SaturationState state) const;
  String to_json(const edge::domain::TelemetrySnapshot& snapshot) const;
};

}  // namespace edge::comms::mqtt
