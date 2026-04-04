#pragma once

namespace edge::comms::mqtt::topic {

constexpr const char* kAckTypeParseError = "parse_error";
constexpr const char* kAckTypeValidationError = "validation_error";
constexpr const char* kAckTypeApplied = "applied";
constexpr const char* kAckTypeStaged = "staged";
constexpr const char* kAckTypePendingApplied = "pending_applied";

constexpr const char* kReasonParseFailed = "payload_parse_failed";
constexpr const char* kReasonAppliedOk = "applied_ok";
constexpr const char* kReasonStagedWaiting = "staged_waiting";
constexpr const char* kReasonPendingApplied = "pending_params_applied";

constexpr const char* kSaturationLow = "low";
constexpr const char* kSaturationNone = "none";
constexpr const char* kSaturationHigh = "high";

}  // namespace edge::comms::mqtt::topic
