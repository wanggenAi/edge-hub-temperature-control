#include "comms/mqtt/param_update_handler.h"

#include <Arduino.h>

namespace edge::comms::mqtt {

ParamUpdateHandler::ParamUpdateHandler(const Dependencies& deps) : deps_(deps) {}

void ParamUpdateHandler::publish_ack_message(
    const edge::domain::ParameterAckMessage& message) const {
  if (deps_.publish_ack == nullptr || deps_.ack_builder == nullptr) {
    return;
  }
  const String payload = deps_.ack_builder->to_json(message);
  deps_.publish_ack(payload, deps_.publish_ack_ctx);
}

void ParamUpdateHandler::on_params_message(const String& payload, unsigned long now_ms) {
  if (deps_.store == nullptr || deps_.parser == nullptr || deps_.validator == nullptr ||
      deps_.ack_builder == nullptr) {
    return;
  }

  edge::domain::ParameterSetMessage message;
  if (!deps_.parser->parse(payload, &message)) {
    Serial.println("params_update_parsed=false");
    publish_ack_message(deps_.ack_builder->build(
        deps_.device_id, deps_.store->current(), topic::kAckTypeParseError, false, false,
        false, topic::kReasonParseFailed, now_ms));
    return;
  }
  Serial.println("params_update_parsed=true");

  const char* validation_reason = deps_.validator->validate(message);
  if (validation_reason[0] != 'o' || validation_reason[1] != 'k' ||
      validation_reason[2] != '\0') {
    Serial.println("params_update_applied=false");
    publish_ack_message(deps_.ack_builder->build(
        deps_.device_id, deps_.store->current(), topic::kAckTypeValidationError, false,
        false, false, validation_reason, now_ms));
    return;
  }

  const bool should_apply_immediately =
      message.has_apply_immediately && message.apply_immediately;

  if (should_apply_immediately) {
    deps_.store->apply_now(message);
    Serial.println("params_update_applied=true");
    if (deps_.on_runtime_applied != nullptr) {
      deps_.on_runtime_applied(true, deps_.on_runtime_applied_ctx);
    }
    publish_ack_message(deps_.ack_builder->build(
        deps_.device_id, deps_.store->current(), topic::kAckTypeApplied, true, true,
        false, topic::kReasonAppliedOk, now_ms));
    return;
  }

  deps_.store->stage(message, now_ms);
  Serial.println("params_update_applied=false");
  Serial.println("params_update_staged=true");
  Serial.print("pending_params_received_ms=");
  Serial.println(now_ms);
  Serial.println("params_apply_mode=staged_waiting");
  publish_ack_message(deps_.ack_builder->build(
      deps_.device_id, deps_.store->current(), topic::kAckTypeStaged, true, false,
      deps_.store->has_pending(), topic::kReasonStagedWaiting, now_ms));
}

void ParamUpdateHandler::apply_pending_if_needed(unsigned long now_ms) {
  if (deps_.store == nullptr || deps_.ack_builder == nullptr) {
    return;
  }

  if (!deps_.store->apply_pending_if_any(now_ms)) {
    return;
  }
  Serial.println("pending_params_applied=true");
  Serial.print("pending_params_applied_ms=");
  Serial.println(now_ms);

  if (deps_.on_runtime_applied != nullptr) {
    deps_.on_runtime_applied(true, deps_.on_runtime_applied_ctx);
  }

  publish_ack_message(deps_.ack_builder->build(
      deps_.device_id, deps_.store->current(), topic::kAckTypePendingApplied, true,
      false, deps_.store->has_pending(), topic::kReasonPendingApplied, now_ms));
}

}  // namespace edge::comms::mqtt
