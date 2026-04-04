#include "comms/mqtt/param_message_parser.h"

#include <string.h>

namespace edge::comms::mqtt {

bool ParamMessageParser::extract_float_field(const String& payload,
                                             const char* key,
                                             float* value) const {
  const String quoted_key = String("\"") + key + "\"";
  const int key_start = payload.indexOf(quoted_key);
  if (key_start < 0) {
    return false;
  }

  const int colon = payload.indexOf(':', key_start + quoted_key.length());
  if (colon < 0) {
    return false;
  }

  int value_start = colon + 1;
  while (value_start < payload.length() &&
         (payload[value_start] == ' ' || payload[value_start] == '"')) {
    ++value_start;
  }

  int value_end = value_start;
  while (value_end < payload.length()) {
    const char current = payload[value_end];
    if (current == ',' || current == '}' || current == '"') {
      break;
    }
    ++value_end;
  }

  const String text = payload.substring(value_start, value_end);
  if (text.length() == 0) {
    return false;
  }

  *value = text.toFloat();
  return true;
}

bool ParamMessageParser::extract_unsigned_long_field(const String& payload,
                                                     const char* key,
                                                     uint32_t* value) const {
  float parsed = 0.0f;
  if (!extract_float_field(payload, key, &parsed)) {
    return false;
  }
  *value = static_cast<uint32_t>(parsed);
  return true;
}

bool ParamMessageParser::extract_bool_field(const String& payload,
                                            const char* key,
                                            bool* value) const {
  const String quoted_key = String("\"") + key + "\"";
  const int key_start = payload.indexOf(quoted_key);
  if (key_start < 0) {
    return false;
  }

  const int colon = payload.indexOf(':', key_start + quoted_key.length());
  if (colon < 0) {
    return false;
  }

  int value_start = colon + 1;
  while (value_start < payload.length() && payload[value_start] == ' ') {
    ++value_start;
  }

  if (payload.startsWith("true", value_start)) {
    *value = true;
    return true;
  }
  if (payload.startsWith("false", value_start)) {
    *value = false;
    return true;
  }
  return false;
}

bool ParamMessageParser::extract_string_field(const String& payload,
                                              const char* key,
                                              char* value,
                                              size_t value_size) const {
  const String quoted_key = String("\"") + key + "\"";
  const int key_start = payload.indexOf(quoted_key);
  if (key_start < 0) {
    return false;
  }

  const int colon = payload.indexOf(':', key_start + quoted_key.length());
  if (colon < 0) {
    return false;
  }

  const int first_quote = payload.indexOf('"', colon + 1);
  if (first_quote < 0) {
    return false;
  }

  const int second_quote = payload.indexOf('"', first_quote + 1);
  if (second_quote < 0) {
    return false;
  }

  const String text = payload.substring(first_quote + 1, second_quote);
  if (value_size == 0) {
    return false;
  }

  strncpy(value, text.c_str(), value_size - 1);
  value[value_size - 1] = '\0';
  return true;
}

bool ParamMessageParser::parse(const String& payload,
                               edge::domain::ParameterSetMessage* out) const {
  *out = {};
  bool has_any = false;

  if (extract_float_field(payload, "target_temp_c", &out->target_temp_c)) {
    out->has_target_temp_c = true;
    has_any = true;
  }
  if (extract_float_field(payload, "kp", &out->kp)) {
    out->has_kp = true;
    has_any = true;
  }
  if (extract_float_field(payload, "ki", &out->ki)) {
    out->has_ki = true;
    has_any = true;
  }
  if (extract_float_field(payload, "kd", &out->kd)) {
    out->has_kd = true;
    has_any = true;
  }
  if (extract_unsigned_long_field(payload, "control_period_ms", &out->control_period_ms)) {
    out->has_control_period_ms = true;
    has_any = true;
  }
  if (extract_string_field(payload, "control_mode", out->control_mode,
                           sizeof(out->control_mode))) {
    out->has_control_mode = true;
    has_any = true;
  }
  if (extract_bool_field(payload, "apply_immediately", &out->apply_immediately)) {
    out->has_apply_immediately = true;
    has_any = true;
  }

  return has_any;
}

}  // namespace edge::comms::mqtt
