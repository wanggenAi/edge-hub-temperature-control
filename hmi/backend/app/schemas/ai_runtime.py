from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class AIRuntimeConfigOut(BaseModel):
    problem_classifier_enabled: bool
    success_predictor_enabled: bool
    preview_gap_predictor_enabled: bool
    candidate_ranker_enabled: bool
    problem_classifier_model_path: str
    success_model_path: str
    preview_gap_model_path: str
    success_model_variant: str
    preview_gap_model_variant: str
    ranker_alpha: float
    ranker_beta: float
    high_gap_penalty_threshold: float
    ranker_candidate_count: int
    use_problem_classifier_for_candidate_bias: bool


class AIRuntimeConfigUpdate(BaseModel):
    problem_classifier_enabled: Optional[bool] = None
    success_predictor_enabled: Optional[bool] = None
    preview_gap_predictor_enabled: Optional[bool] = None
    candidate_ranker_enabled: Optional[bool] = None
    problem_classifier_model_path: Optional[str] = None
    success_model_path: Optional[str] = None
    preview_gap_model_path: Optional[str] = None
    success_model_variant: Optional[str] = None
    preview_gap_model_variant: Optional[str] = None
    ranker_alpha: Optional[float] = None
    ranker_beta: Optional[float] = None
    high_gap_penalty_threshold: Optional[float] = None
    ranker_candidate_count: Optional[int] = None
    use_problem_classifier_for_candidate_bias: Optional[bool] = None


class AIRuntimeModelStateOut(BaseModel):
    enabled: bool
    loaded: bool
    available: bool
    path: Optional[str] = None
    variant: Optional[str] = None
    error: Optional[str] = None


class AIRuntimeStatusOut(BaseModel):
    problem_classifier: AIRuntimeModelStateOut
    success_predictor: AIRuntimeModelStateOut
    preview_gap_predictor: AIRuntimeModelStateOut
    candidate_ranker: AIRuntimeModelStateOut


class AIRuntimeRecommendationDebugOut(BaseModel):
    device_id: Optional[int] = None
    recommendation_id: Optional[int] = None
    source: str
    generated_at: datetime
    decision: dict[str, Any]

