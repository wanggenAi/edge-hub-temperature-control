#include "app/runtime_config_store.h"

#include <string.h>

namespace edge::app {

RuntimeConfigStore::RuntimeConfigStore(const edge::domain::RuntimeControlConfig& initial)
    : current_(initial) {}

const edge::domain::RuntimeControlConfig& RuntimeConfigStore::current() const {
  return current_;
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
