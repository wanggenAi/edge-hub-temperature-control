#include "app/runtime_config_store.h"

#include <Arduino.h>
#include <Preferences.h>
#include <string.h>

namespace edge::app {

namespace {

constexpr char kPrefsNamespace[] = "edge_runtime";
constexpr char kSchemaKey[] = "schema";
constexpr uint32_t kSchemaVersion = 1;

void print_runtime_config_values(const char* prefix,
                                 const edge::domain::RuntimeControlConfig& config) {
  Serial.print(prefix);
  Serial.print("_target_temp_c=");
  Serial.println(config.target_temp_c, 2);
  Serial.print(prefix);
  Serial.print("_kp=");
  Serial.println(config.kp, 2);
  Serial.print(prefix);
  Serial.print("_ki=");
  Serial.println(config.ki, 2);
  Serial.print(prefix);
  Serial.print("_kd=");
  Serial.println(config.kd, 2);
  Serial.print(prefix);
  Serial.print("_control_period_ms=");
  Serial.println(config.control_period_ms);
  Serial.print(prefix);
  Serial.print("_control_mode=");
  Serial.println(config.control_mode);
}

}  // namespace

RuntimeConfigStore::RuntimeConfigStore(const edge::domain::RuntimeControlConfig& initial)
    : current_(initial) {}

const edge::domain::RuntimeControlConfig& RuntimeConfigStore::current() const {
  return current_;
}

bool RuntimeConfigStore::load_persisted() {
  Preferences prefs;
  if (!prefs.begin(kPrefsNamespace, false)) {
    Serial.println("runtime_config_load_status=prefs_open_failed");
    return false;
  }

  const bool has_runtime_config = prefs.isKey(kSchemaKey);
  if (!has_runtime_config) {
    prefs.end();
    Serial.println("runtime_config_load_status=no_persisted_config");
    print_runtime_config_values("runtime_config_default", current_);
    return false;
  }

  const uint32_t schema = prefs.getUInt(kSchemaKey, 0);
  if (schema != kSchemaVersion) {
    prefs.end();
    Serial.println("runtime_config_load_status=unsupported_schema");
    Serial.print("runtime_config_loaded_schema=");
    Serial.println(schema);
    print_runtime_config_values("runtime_config_default", current_);
    return false;
  }

  current_.target_temp_c = prefs.getFloat("target", current_.target_temp_c);
  current_.kp = prefs.getFloat("kp", current_.kp);
  current_.ki = prefs.getFloat("ki", current_.ki);
  current_.kd = prefs.getFloat("kd", current_.kd);
  current_.control_period_ms = prefs.getUInt("period", current_.control_period_ms);
  const size_t mode_len =
      prefs.getString("mode", current_.control_mode, sizeof(current_.control_mode));
  if (mode_len == 0) {
    current_.control_mode[sizeof(current_.control_mode) - 1] = '\0';
  }
  prefs.end();

  has_pending_ = false;
  pending_since_ms_ = 0;
  pending_ = {};
  Serial.println("runtime_config_load_status=loaded_from_nvs");
  Serial.print("runtime_config_loaded_schema=");
  Serial.println(schema);
  print_runtime_config_values("runtime_config_loaded", current_);
  return true;
}

bool RuntimeConfigStore::save_current() const {
  Preferences prefs;
  if (!prefs.begin(kPrefsNamespace, false)) {
    Serial.println("runtime_config_save_status=prefs_open_failed");
    return false;
  }

  bool ok = true;
  ok = prefs.putUInt(kSchemaKey, kSchemaVersion) > 0 && ok;
  ok = prefs.putFloat("target", current_.target_temp_c) > 0 && ok;
  ok = prefs.putFloat("kp", current_.kp) > 0 && ok;
  ok = prefs.putFloat("ki", current_.ki) > 0 && ok;
  ok = prefs.putFloat("kd", current_.kd) > 0 && ok;
  ok = prefs.putUInt("period", current_.control_period_ms) > 0 && ok;
  ok = prefs.putString("mode", current_.control_mode) > 0 && ok;
  prefs.end();

  Serial.print("runtime_config_save_status=");
  Serial.println(ok ? "saved_to_nvs" : "failed");
  print_runtime_config_values("runtime_config_saved", current_);
  return ok;
}

void RuntimeConfigStore::apply_into(edge::domain::RuntimeControlConfig* target,
                                    const edge::domain::ParameterSetMessage& msg) {
  if (msg.has_target_temp_c) {
    target->target_temp_c = msg.target_temp_c;
  }
  if (msg.has_kp) {
    target->kp = msg.kp;
  }
  if (msg.has_ki) {
    target->ki = msg.ki;
  }
  if (msg.has_kd) {
    target->kd = msg.kd;
  }
  if (msg.has_control_period_ms) {
    target->control_period_ms = msg.control_period_ms;
  }
  if (msg.has_control_mode) {
    strncpy(target->control_mode, msg.control_mode, sizeof(target->control_mode) - 1);
    target->control_mode[sizeof(target->control_mode) - 1] = '\0';
  }
}

void RuntimeConfigStore::apply_now(const edge::domain::ParameterSetMessage& msg) {
  apply_into(&current_, msg);
  has_pending_ = false;
  pending_since_ms_ = 0;
  pending_ = {};
}

void RuntimeConfigStore::stage(const edge::domain::ParameterSetMessage& msg,
                               unsigned long now_ms) {
  pending_ = msg;
  has_pending_ = true;
  pending_since_ms_ = now_ms;
}

bool RuntimeConfigStore::has_pending() const { return has_pending_; }

unsigned long RuntimeConfigStore::pending_age_ms(unsigned long now_ms) const {
  if (!has_pending_) {
    return 0;
  }
  return now_ms - pending_since_ms_;
}

bool RuntimeConfigStore::apply_pending_if_any(unsigned long now_ms) {
  if (!has_pending_) {
    return false;
  }

  apply_into(&current_, pending_);
  has_pending_ = false;
  pending_since_ms_ = 0;
  pending_ = {};
  (void)now_ms;
  return true;
}

}  // namespace edge::app
