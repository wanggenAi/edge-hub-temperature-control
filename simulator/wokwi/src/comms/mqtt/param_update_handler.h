#pragma once

#include "app/runtime_config_store.h"
#include "comms/mqtt/ack_builder.h"
#include "comms/mqtt/param_message_parser.h"
#include "comms/mqtt/param_validator.h"
#include "comms/mqtt/topic_registry.h"

namespace edge::comms::mqtt {

class ParamUpdateHandler {
 public:
  struct Dependencies {
    const char* device_id = "";
    edge::app::RuntimeConfigStore* store = nullptr;
    const ParamMessageParser* parser = nullptr;
    const ParamValidator* validator = nullptr;
    const AckBuilder* ack_builder = nullptr;

    bool (*publish_ack)(const String& payload, void* ctx) = nullptr;
    void* publish_ack_ctx = nullptr;

    void (*on_runtime_applied)(bool reset_integral, void* ctx) = nullptr;
    void* on_runtime_applied_ctx = nullptr;

    void (*enrich_ack)(edge::domain::ParameterAckMessage* message, void* ctx) = nullptr;
    void* enrich_ack_ctx = nullptr;
  };

  explicit ParamUpdateHandler(const Dependencies& deps);

  void on_params_message(const String& payload, unsigned long now_ms);
  void apply_pending_if_needed(unsigned long now_ms);

 private:
  void publish_ack_message(const edge::domain::ParameterAckMessage& message) const;

  Dependencies deps_;
};

}  // namespace edge::comms::mqtt
