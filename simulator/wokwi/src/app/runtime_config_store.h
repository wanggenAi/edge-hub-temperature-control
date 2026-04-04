#pragma once

#include "domain/model/param_messages.h"
#include "domain/model/runtime_config.h"

namespace edge::app {

class RuntimeConfigStore {
 public:
  explicit RuntimeConfigStore(const edge::domain::RuntimeControlConfig& initial);

  const edge::domain::RuntimeControlConfig& current() const;
  void apply_now(const edge::domain::ParameterSetMessage& msg);
  void stage(const edge::domain::ParameterSetMessage& msg, unsigned long now_ms);
  bool has_pending() const;
  unsigned long pending_age_ms(unsigned long now_ms) const;
  bool apply_pending_if_any(unsigned long now_ms);

 private:
  void apply_into(edge::domain::RuntimeControlConfig* target,
                  const edge::domain::ParameterSetMessage& msg);

  edge::domain::RuntimeControlConfig current_;
  edge::domain::ParameterSetMessage pending_;
  bool has_pending_ = false;
  unsigned long pending_since_ms_ = 0;
};

}  // namespace edge::app
