#pragma once

namespace edge::app {

// 逐步搬迁入口：先保留为空实现，再把旧 sketch 逻辑按职责迁入这里。
struct MigrationHooks {
  void (*before_control_tick)() = nullptr;
  void (*after_control_tick)() = nullptr;
};

}  // namespace edge::app
