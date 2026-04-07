from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Any, Optional, Union

from app.services.ai.feature_extractor import extract_features
from app.services.ai.problem_classifier import classify_problem
from app.services.ai.schemas import PIDParams, RecommendationGenerateInput, RecommendationGenerateOutput
from app.services.ai.tuning_engine import build_recommendation


class RecommendationService:
    _LEGACY_GAIN_PATTERN = re.compile(r"(Kp|Ki|Kd)\s*:\s*([+-]?\d+(?:\.\d+)?)")
    _FLOAT_PRECISION = 4
    # Suggestion is stored in ai_recommendations.suggestion (TEXT).
    # Keep a generous soft cap only as a safety guard against accidental bloat.
    _SUGGESTION_MAX_LEN = 16384
    _BROKEN_PID_FIELD_PATTERN = re.compile(r"\"(kp|ki|kd)\"\s*:\s*([+-]?\d+(?:\.\d+)?)", flags=re.IGNORECASE)

    @classmethod
    def _round(cls, value: float) -> float:
        return round(float(value), cls._FLOAT_PRECISION)

    @classmethod
    def _normalize_pid(cls, params: PIDParams) -> dict[str, float]:
        return {
            "kp": cls._round(params.kp),
            "ki": cls._round(params.ki),
            "kd": cls._round(params.kd),
        }

    def generate(self, payload: RecommendationGenerateInput) -> RecommendationGenerateOutput:
        features = extract_features(payload)
        problem_type, confidence, rules = classify_problem(payload, features)
        current_params, recommended_params, delta, risk_level, requires_confirmation, expected_effect = build_recommendation(
            problem_type, payload.current_params
        )

        evidence: dict[str, Union[float, int, str, bool, None]] = {
            "rule_saturation_limited": rules.get("saturation_limited", False),
            "rule_oscillation": rules.get("oscillation", False),
            "rule_overshoot_high": rules.get("overshoot_high", False),
            "rule_steady_state_error": rules.get("steady_state_error", False),
            "rule_slow_response": rules.get("slow_response", False),
            "mean_error": round(features.mean_error, 4),
            "mean_abs_error": round(features.mean_abs_error, 4),
            "error_std": round(features.error_std, 4),
            "temp_swing": round(features.temp_swing, 4),
            "pwm_mean": round(features.pwm_mean, 4),
            "pwm_max": round(features.pwm_max, 4),
            "zero_crossings": features.zero_crossings,
            "in_band_ratio": round(features.in_band_ratio, 4),
            "overshoot_pct": round(features.overshoot_pct, 4),
            "settling_sec": None if features.settling_sec is None else round(features.settling_sec, 4),
            "saturation_ratio": round(features.saturation_ratio, 4),
        }

        return RecommendationGenerateOutput(
            problem_type=problem_type,
            confidence=round(confidence, 4),
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
            current_params=current_params,
            recommended_params=recommended_params,
            delta=delta,
            expected_effect=expected_effect,
            evidence=evidence,
            generated_at=datetime.utcnow(),
        )

    def build_recommendation_fingerprint(self, output: RecommendationGenerateOutput) -> str:
        canonical = {
            "problem_type": output.problem_type.value,
            "expected_effect": output.expected_effect.value,
            "risk_level": output.risk_level.value,
            "requires_confirmation": bool(output.requires_confirmation),
            "current_params": self._normalize_pid(output.current_params),
            "recommended_params": self._normalize_pid(output.recommended_params),
            "delta": self._normalize_pid(output.delta),
        }
        serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def _is_close(cls, left: float, right: float, tolerance: float) -> bool:
        return abs(float(left) - float(right)) <= tolerance

    def is_effectively_same_recommendation(
        self,
        current: RecommendationGenerateOutput,
        previous: RecommendationGenerateOutput,
        *,
        tolerance: float,
    ) -> bool:
        if current.problem_type.value != previous.problem_type.value:
            return False
        if current.expected_effect.value != previous.expected_effect.value:
            return False
        if current.risk_level.value != previous.risk_level.value:
            return False
        if bool(current.requires_confirmation) != bool(previous.requires_confirmation):
            return False

        current_current = self._normalize_pid(current.current_params)
        previous_current = self._normalize_pid(previous.current_params)
        current_recommended = self._normalize_pid(current.recommended_params)
        previous_recommended = self._normalize_pid(previous.recommended_params)
        current_delta = self._normalize_pid(current.delta)
        previous_delta = self._normalize_pid(previous.delta)
        for key in ("kp", "ki", "kd"):
            if not self._is_close(current_current[key], previous_current[key], tolerance):
                return False
            if not self._is_close(current_recommended[key], previous_recommended[key], tolerance):
                return False
            if not self._is_close(current_delta[key], previous_delta[key], tolerance):
                return False
        return True

    def to_storage_fields(
        self,
        output: RecommendationGenerateOutput,
        *,
        fingerprint: Optional[str] = None,
        history_state: str = "generated",
        last_generate_reused: bool = False,
        reused_count: int = 0,
        last_accessed_at: Optional[datetime] = None,
        runtime_decision: Optional[dict[str, Any]] = None,
    ) -> tuple[str, str, str]:
        reason = f"{output.problem_type.value}; effect={output.expected_effect.value}"
        risk = f"{output.risk_level.value}; requires_confirmation={output.requires_confirmation}"
        recommended = self._normalize_pid(output.recommended_params)
        delta = self._normalize_pid(output.delta)
        current = self._normalize_pid(output.current_params)
        fp = fingerprint or self.build_recommendation_fingerprint(output)
        accessed_at = (last_accessed_at or output.generated_at).isoformat(timespec="seconds")
        metadata = {
            "fp": fp,
            "hs": history_state,
            "lgr": bool(last_generate_reused),
            "rc": int(max(0, reused_count)),
            "la": accessed_at,
        }
        if isinstance(runtime_decision, dict):
            metadata["ard"] = runtime_decision
        suggestion = json.dumps(
            {
                "f": "ai_rec",
                "v": "1",
                "p": {
                    "t": output.problem_type.value,
                    "e": output.expected_effect.value,
                    "r": output.risk_level.value,
                    "c": round(output.confidence, 4),
                    "rc": output.requires_confirmation,
                    "cp": current,
                    "rp": recommended,
                    "d": delta,
                    # Metadata keeps recommendation history semantics without schema migration.
                    "m": metadata,
                },
            },
            separators=(",", ":"),
        )
        return reason, self._fit_suggestion_size(suggestion), risk

    def read_storage_metadata(self, suggestion: str) -> dict[str, Any]:
        if not suggestion:
            return {}
        try:
            body = json.loads(suggestion)
        except (TypeError, ValueError):
            return {}
        if not isinstance(body, dict) or body.get("f") != "ai_rec":
            return {}
        payload = body.get("p")
        if not isinstance(payload, dict):
            return {}
        meta = payload.get("m")
        if not isinstance(meta, dict):
            return {}
        return dict(meta)

    def update_storage_metadata(
        self,
        suggestion: str,
        *,
        history_state: Optional[str] = None,
        fingerprint: Optional[str] = None,
        last_generate_reused: Optional[bool] = None,
        increment_reused_count: bool = False,
        reset_reused_count: bool = False,
        last_accessed_at: Optional[datetime] = None,
        preview_summary: Optional[dict[str, Any]] = None,
        post_effect_summary: Optional[dict[str, Any]] = None,
        post_effect_comparison_before: Optional[dict[str, Any]] = None,
        post_effect_comparison_preview: Optional[dict[str, Any]] = None,
        actual_effect_evaluated: Optional[bool] = None,
        insufficient_data: Optional[bool] = None,
        observation_window_minutes: Optional[int] = None,
        evaluated_at: Optional[datetime] = None,
        applied_at: Optional[datetime] = None,
        runtime_decision: Optional[dict[str, Any]] = None,
    ) -> str:
        if not suggestion:
            return suggestion
        try:
            body = json.loads(suggestion)
        except (TypeError, ValueError):
            return suggestion
        if not isinstance(body, dict) or body.get("f") != "ai_rec":
            return suggestion
        payload = body.get("p")
        if not isinstance(payload, dict):
            return suggestion
        meta = payload.get("m")
        if not isinstance(meta, dict):
            meta = {}
        next_meta = dict(meta)
        if history_state:
            next_meta["hs"] = history_state
        if fingerprint:
            next_meta["fp"] = fingerprint
        if last_generate_reused is not None:
            next_meta["lgr"] = bool(last_generate_reused)
        if reset_reused_count:
            next_meta["rc"] = 0
        if increment_reused_count:
            current_count = int(next_meta.get("rc") or 0)
            next_meta["rc"] = max(0, current_count) + 1
        if last_accessed_at:
            next_meta["la"] = last_accessed_at.isoformat(timespec="seconds")
        if preview_summary is not None:
            next_meta["pvs"] = preview_summary
        if post_effect_summary is not None:
            next_meta["pe"] = post_effect_summary
        if post_effect_comparison_before is not None:
            next_meta["pecb"] = post_effect_comparison_before
        if post_effect_comparison_preview is not None:
            next_meta["pecp"] = post_effect_comparison_preview
        if actual_effect_evaluated is not None:
            next_meta["aee"] = bool(actual_effect_evaluated)
        if insufficient_data is not None:
            next_meta["pei"] = bool(insufficient_data)
        if observation_window_minutes is not None:
            next_meta["pew"] = int(max(1, observation_window_minutes))
        if evaluated_at is not None:
            next_meta["pea"] = evaluated_at.isoformat(timespec="seconds")
        if applied_at is not None:
            next_meta["apa"] = applied_at.isoformat(timespec="seconds")
        if runtime_decision is not None and isinstance(runtime_decision, dict):
            next_meta["ard"] = runtime_decision
        payload["m"] = next_meta
        body["p"] = payload
        return self._fit_suggestion_size(json.dumps(body, separators=(",", ":")))

    def _fit_suggestion_size(self, suggestion: str) -> str:
        if len(suggestion) <= self._SUGGESTION_MAX_LEN:
            return suggestion
        try:
            body = json.loads(suggestion)
        except (TypeError, ValueError):
            return suggestion[: self._SUGGESTION_MAX_LEN]
        if not isinstance(body, dict) or body.get("f") != "ai_rec":
            return suggestion[: self._SUGGESTION_MAX_LEN]
        payload = body.get("p")
        if not isinstance(payload, dict):
            return suggestion[: self._SUGGESTION_MAX_LEN]

        # Drop heavy optional metadata first.
        meta = payload.get("m")
        if isinstance(meta, dict):
            for key in ("pvs", "pecb", "pecp", "ard"):
                meta.pop(key, None)
            if "pe" in meta and isinstance(meta.get("pe"), dict):
                pe = meta.get("pe") or {}
                meta["pe"] = {
                    "ib": pe.get("in_band_ratio_after"),
                    "ov": pe.get("overshoot_c_after"),
                    "st": pe.get("settling_sec_after"),
                    "ma": pe.get("mean_abs_error_after"),
                    "sr": pe.get("saturation_ratio_after"),
                    "sw": pe.get("temp_swing_after"),
                    "pc": pe.get("point_count"),
                }
            payload["m"] = meta

        body["p"] = payload
        compact = json.dumps(body, separators=(",", ":"))
        if len(compact) <= self._SUGGESTION_MAX_LEN:
            return compact
        if "cp" in payload:
            payload.pop("cp", None)
            body["p"] = payload
            compact_no_cp = json.dumps(body, separators=(",", ":"))
            if len(compact_no_cp) <= self._SUGGESTION_MAX_LEN:
                return compact_no_cp

        # Keep minimum viable recommendation payload.
        # Prefer preserving metadata + recommended params so history/apply/evaluation
        # semantics remain readable even when suggestion text must be compacted.
        tiny = {
            "f": "ai_rec",
            "v": body.get("v", "1"),
            "p": {
                "rp": payload.get("rp"),
                "m": {},
            },
        }
        if isinstance(payload.get("m"), dict):
            tiny_meta = payload.get("m") or {}
            tiny["p"]["m"] = {
                k: tiny_meta.get(k)
                for k in ("fp", "hs", "lgr", "rc", "la", "apa", "aee", "pei", "pew", "pea")
                if k in tiny_meta
            }
        compact_tiny = json.dumps(tiny, separators=(",", ":"))
        if len(compact_tiny) <= self._SUGGESTION_MAX_LEN:
            return compact_tiny

        rp = payload.get("rp") if isinstance(payload.get("rp"), dict) else {}
        kp = self._round(float(rp.get("kp", 0.0) or 0.0))
        ki = self._round(float(rp.get("ki", 0.0) or 0.0))
        kd = self._round(float(rp.get("kd", 0.0) or 0.0))
        # Guaranteed short legacy fallback (always parseable by current parser).
        legacy = f"Kp:{kp:+.4f} Ki:{ki:+.4f} Kd:{kd:+.4f}"
        return legacy[: self._SUGGESTION_MAX_LEN]

    def build_output_from_storage(
        self,
        *,
        reason: str,
        suggestion: str,
        risk: str,
        confidence: float,
        generated_at: datetime,
        fallback_current_params: PIDParams,
    ) -> Optional[RecommendationGenerateOutput]:
        parsed = self.parse_suggestion_payload(suggestion)
        if not parsed:
            return None
        recommended = parsed.get("recommended_params")
        if not isinstance(recommended, dict):
            return None
        delta = parsed.get("delta")
        if not isinstance(delta, dict):
            delta = {
                "kp": self._round(float(recommended.get("kp", fallback_current_params.kp)) - float(fallback_current_params.kp)),
                "ki": self._round(float(recommended.get("ki", fallback_current_params.ki)) - float(fallback_current_params.ki)),
                "kd": self._round(float(recommended.get("kd", fallback_current_params.kd)) - float(fallback_current_params.kd)),
            }
        current = parsed.get("current_params")
        if not isinstance(current, dict):
            current = self._normalize_pid(fallback_current_params)

        reason_problem, reason_effect = self.parse_reason_fields(reason)
        risk_level, requires_confirmation = self.parse_risk_fields(risk)
        problem_type = parsed.get("problem_type") or reason_problem or "normal"
        expected_effect = parsed.get("expected_effect") or reason_effect or "keep_stable"
        risk_text = parsed.get("risk_level") or risk_level or "Low"
        requires = parsed.get("requires_confirmation")
        if requires is None:
            requires = bool(requires_confirmation) if requires_confirmation is not None else False
        evidence = parsed.get("evidence") if isinstance(parsed.get("evidence"), dict) else {}

        try:
            output = RecommendationGenerateOutput(
                problem_type=problem_type,
                confidence=self._round(float(confidence)),
                risk_level=risk_text,
                requires_confirmation=bool(requires),
                current_params=PIDParams(
                    kp=float(current.get("kp", fallback_current_params.kp)),
                    ki=float(current.get("ki", fallback_current_params.ki)),
                    kd=float(current.get("kd", fallback_current_params.kd)),
                ),
                recommended_params=PIDParams(
                    kp=float(recommended.get("kp", fallback_current_params.kp)),
                    ki=float(recommended.get("ki", fallback_current_params.ki)),
                    kd=float(recommended.get("kd", fallback_current_params.kd)),
                ),
                delta=PIDParams(
                    kp=float(delta.get("kp", 0.0)),
                    ki=float(delta.get("ki", 0.0)),
                    kd=float(delta.get("kd", 0.0)),
                ),
                expected_effect=expected_effect,
                evidence=evidence,
                generated_at=generated_at,
            )
            meta = self.read_storage_metadata(suggestion)
            if isinstance(meta.get("fp"), str):
                output.fingerprint = str(meta.get("fp"))
            if isinstance(meta.get("hs"), str):
                output.history_state = str(meta.get("hs"))
            if isinstance(meta.get("lgr"), bool):
                output.last_generate_reused = bool(meta.get("lgr"))
            if isinstance(meta.get("rc"), (int, float, str)):
                try:
                    output.reused_count = max(0, int(meta.get("rc")))
                except (TypeError, ValueError):
                    output.reused_count = 0
            if isinstance(meta.get("la"), str):
                try:
                    output.last_accessed_at = datetime.fromisoformat(str(meta.get("la")).replace("Z", "+00:00"))
                except ValueError:
                    output.last_accessed_at = generated_at
            return output
        except Exception:
            return None

    @staticmethod
    def parse_reason_fields(reason: str) -> tuple[Optional[str], Optional[str]]:
        if not reason:
            return None, None
        text = reason.strip()
        if not text:
            return None, None
        effect_match = re.search(r"effect=([a-z_]+)", text, flags=re.IGNORECASE)
        prefix = text.split(";")[0].strip() if ";" in text else text
        problem = prefix if prefix and "=" not in prefix else None
        return problem, effect_match.group(1) if effect_match else None

    @staticmethod
    def parse_risk_fields(risk: str) -> tuple[Optional[str], Optional[bool]]:
        if not risk:
            return None, None
        text = risk.strip()
        if not text:
            return None, None
        level_match = re.search(r"^(Low|Medium|High)\b", text, flags=re.IGNORECASE)
        confirm_match = re.search(r"requires_confirmation\s*=\s*(true|false)", text, flags=re.IGNORECASE)
        level = level_match.group(1).capitalize() if level_match else None
        confirm = None
        if confirm_match:
            confirm = confirm_match.group(1).lower() == "true"
        return level, confirm

    def parse_suggestion_payload(self, suggestion: str) -> Optional[dict[str, Any]]:
        if not suggestion:
            return None
        try:
            body = json.loads(suggestion)
        except (TypeError, ValueError):
            return None
        if not isinstance(body, dict):
            return None
        parsed: dict[str, Any] = {}

        if body.get("f") == "ai_rec" and isinstance(body.get("p"), dict):
            payload = body["p"]
            if isinstance(payload.get("t"), str):
                parsed["problem_type"] = payload.get("t")
            if isinstance(payload.get("e"), str):
                parsed["expected_effect"] = payload.get("e")
            if isinstance(payload.get("r"), str):
                parsed["risk_level"] = payload.get("r")
            if isinstance(payload.get("rc"), bool):
                parsed["requires_confirmation"] = payload.get("rc")
            if isinstance(payload.get("evidence"), dict):
                parsed["evidence"] = payload.get("evidence")
            if isinstance(payload.get("cp"), dict):
                parsed["current_params"] = payload.get("cp")
            if isinstance(payload.get("rp"), dict):
                parsed["recommended_params"] = payload.get("rp")
            if isinstance(payload.get("d"), dict):
                parsed["delta"] = payload.get("d")
            return parsed

        payload_obj = body.get("payload") if isinstance(body.get("payload"), dict) else body
        if isinstance(payload_obj, dict):
            if isinstance(payload_obj.get("problem_type"), str):
                parsed["problem_type"] = payload_obj.get("problem_type")
            if isinstance(payload_obj.get("expected_effect"), str):
                parsed["expected_effect"] = payload_obj.get("expected_effect")
            if isinstance(payload_obj.get("risk_level"), str):
                parsed["risk_level"] = payload_obj.get("risk_level")
            if isinstance(payload_obj.get("requires_confirmation"), bool):
                parsed["requires_confirmation"] = payload_obj.get("requires_confirmation")
            if isinstance(payload_obj.get("evidence"), dict):
                parsed["evidence"] = payload_obj.get("evidence")
            if isinstance(payload_obj.get("current_params"), dict):
                parsed["current_params"] = payload_obj.get("current_params")
            if isinstance(payload_obj.get("recommended_params"), dict):
                parsed["recommended_params"] = payload_obj.get("recommended_params")
            if isinstance(payload_obj.get("delta"), dict):
                parsed["delta"] = payload_obj.get("delta")
            if parsed:
                return parsed
        return None

    def parse_recommended_params(self, suggestion: str, current_params: PIDParams) -> Optional[PIDParams]:
        if not suggestion:
            return None

        try:
            body = json.loads(suggestion)
            if isinstance(body, dict) and body.get("f") == "ai_rec":
                compact_payload = body.get("p")
                if isinstance(compact_payload, dict):
                    rec = compact_payload.get("rp")
                    if isinstance(rec, dict):
                        return PIDParams(
                            kp=float(rec.get("kp", current_params.kp)),
                            ki=float(rec.get("ki", current_params.ki)),
                            kd=float(rec.get("kd", current_params.kd)),
                        )
                    delta = compact_payload.get("d")
                    if isinstance(delta, dict):
                        return PIDParams(
                            kp=round(current_params.kp + float(delta.get("kp", 0.0)), 4),
                            ki=round(current_params.ki + float(delta.get("ki", 0.0)), 4),
                            kd=round(current_params.kd + float(delta.get("kd", 0.0)), 4),
                        )

            payload = body.get("payload") if isinstance(body, dict) else None
            if isinstance(payload, dict):
                rec = payload.get("recommended_params")
                if isinstance(rec, dict):
                    return PIDParams(
                        kp=float(rec.get("kp", current_params.kp)),
                        ki=float(rec.get("ki", current_params.ki)),
                        kd=float(rec.get("kd", current_params.kd)),
                    )
                delta = payload.get("delta")
                if isinstance(delta, dict):
                    return PIDParams(
                        kp=round(current_params.kp + float(delta.get("kp", 0.0)), 4),
                        ki=round(current_params.ki + float(delta.get("ki", 0.0)), 4),
                        kd=round(current_params.kd + float(delta.get("kd", 0.0)), 4),
                    )
        except (ValueError, TypeError):
            # Recover from truncated JSON payload by extracting visible kp/ki/kd fields.
            recovered: dict[str, float] = {}
            for key, value in self._BROKEN_PID_FIELD_PATTERN.findall(suggestion):
                try:
                    lowered = key.lower()
                    # Prefer first occurrence (usually recommended_params.rp), avoid overriding with delta.d.
                    recovered.setdefault(lowered, float(value))
                except (TypeError, ValueError):
                    continue
            if recovered:
                return PIDParams(
                    kp=float(recovered.get("kp", current_params.kp)),
                    ki=float(recovered.get("ki", current_params.ki)),
                    kd=float(recovered.get("kd", current_params.kd)),
                )

        updates: dict[str, float] = {}
        for key, value in self._LEGACY_GAIN_PATTERN.findall(suggestion):
            updates[key.lower()] = float(value)
        if not updates:
            return None
        return PIDParams(
            kp=round(current_params.kp + updates.get("kp", 0.0), 4),
            ki=round(current_params.ki + updates.get("ki", 0.0), 4),
            kd=round(current_params.kd + updates.get("kd", 0.0), 4),
        )
