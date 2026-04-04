#pragma once

#include "domain/model/param_messages.h"

namespace edge::comms::mqtt {

class ParamMessageParser {
 public:
  bool parse(const String& payload, edge::domain::ParameterSetMessage* out) const;

 private:
  bool extract_float_field(const String& payload, const char* key, float* value) const;
  bool extract_unsigned_long_field(const String& payload,
                                   const char* key,
                                   uint32_t* value) const;
  bool extract_bool_field(const String& payload, const char* key, bool* value) const;
  bool extract_string_field(const String& payload,
                            const char* key,
                            char* value,
                            size_t value_size) const;
};

}  // namespace edge::comms::mqtt
