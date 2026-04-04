#pragma once

namespace edge::app {

// Progressive migration hooks: keep empty at first, then move legacy sketch
// logic into these callbacks by responsibility.
struct MigrationHooks {
  void (*before_control_tick)() = nullptr;
  void (*after_control_tick)() = nullptr;
};

}  // namespace edge::app
