from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import ControlActionFeedbackSample, ModelLifecycleRun


@dataclass(frozen=True)
class FamilySpec:
    key: str
    train_script: str
    artifact_prefix: str
    metrics_file: str
    danger_label: str
    dangerous_pred_labels: tuple[str, ...]


FAMILIES: tuple[FamilySpec, ...] = (
    FamilySpec(
        key="recommendation_success",
        train_script="hmi/backend/ai/scripts/train_recommendation_success_model.py",
        artifact_prefix="recommendation_success",
        metrics_file="recommendation_success_metrics.json",
        danger_label="worse",
        dangerous_pred_labels=("unchanged", "improved"),
    ),
    FamilySpec(
        key="preview_gap",
        train_script="hmi/backend/ai/scripts/train_preview_gap_model.py",
        artifact_prefix="preview_gap",
        metrics_file="preview_gap_metrics.json",
        danger_label="high",
        dangerous_pred_labels=("medium", "low"),
    ),
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


class ModelLifecycleService:
    def __init__(self) -> None:
        self.repo_root = _repo_root()
        self.backend_root = self.repo_root / "hmi/backend"
        self.active_root = self.backend_root / "artifacts/active"
        self.candidates_root = self.backend_root / "artifacts/candidates"
        self.archive_root = self.backend_root / "artifacts/archive"

    def _last_completed_at(self, db: Session) -> Optional[datetime]:
        return db.scalar(select(func.max(ModelLifecycleRun.completed_at)).where(ModelLifecycleRun.completed_at.is_not(None)))

    def _last_started_at(self, db: Session) -> Optional[datetime]:
        return db.scalar(select(func.max(ModelLifecycleRun.started_at)))

    def _count_eligible_samples(self, db: Session) -> int:
        return int(
            db.scalar(
                select(func.count(ControlActionFeedbackSample.id)).where(ControlActionFeedbackSample.is_training_eligible.is_(True))
            )
            or 0
        )

    def _count_recent_eligible_7d(self, db: Session, *, now: datetime) -> int:
        return int(
            db.scalar(
                select(func.count(ControlActionFeedbackSample.id)).where(
                    ControlActionFeedbackSample.is_training_eligible.is_(True),
                    ControlActionFeedbackSample.created_at >= (now - timedelta(days=7)),
                )
            )
            or 0
        )

    def _count_new_since_last(self, db: Session, *, last_completed_at: Optional[datetime]) -> int:
        stmt = select(func.count(ControlActionFeedbackSample.id)).where(ControlActionFeedbackSample.is_training_eligible.is_(True))
        if last_completed_at is not None:
            stmt = stmt.where(ControlActionFeedbackSample.created_at > last_completed_at)
        return int(db.scalar(stmt) or 0)

    def _normalize_preview_metric(self, raw: Any, key: str) -> Optional[float]:
        if not isinstance(raw, dict):
            return None
        value = raw.get(key)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _build_training_dataset(self, db: Session, *, out_path: Path) -> int:
        try:
            import pandas as pd  # type: ignore
        except Exception as exc:
            raise RuntimeError(f"pandas_import_failed: {exc}") from exc

        rows = db.scalars(
            select(ControlActionFeedbackSample).where(ControlActionFeedbackSample.is_training_eligible.is_(True))
        ).all()
        items: list[dict[str, Any]] = []
        for s in rows:
            preview = s.preview_metrics_summary if isinstance(s.preview_metrics_summary, dict) else {}
            items.append(
                {
                    "baseline_kp": s.kp_before,
                    "baseline_ki": s.ki_before,
                    "baseline_kd": s.kd_before,
                    "recommended_kp": s.kp_after,
                    "recommended_ki": s.ki_after,
                    "recommended_kd": s.kd_after,
                    "delta_kp": s.delta_kp,
                    "delta_ki": s.delta_ki,
                    "delta_kd": s.delta_kd,
                    "mean_error": s.mean_error,
                    "mean_abs_error": s.mean_abs_error,
                    "error_std": s.error_std,
                    "temp_swing": s.temp_swing,
                    "pwm_mean": s.pwm_mean,
                    "pwm_max": s.pwm_max,
                    "zero_crossings": s.zero_crossings,
                    "in_band_ratio": s.in_band_ratio,
                    "overshoot_pct": s.overshoot_pct,
                    "settling_sec": s.settling_sec,
                    "saturation_ratio": s.saturation_ratio,
                    "preview_in_band_ratio": self._normalize_preview_metric(preview, "in_band_ratio"),
                    "preview_overshoot_c": self._normalize_preview_metric(preview, "overshoot_c"),
                    "preview_settling_sec": self._normalize_preview_metric(preview, "settling_sec"),
                    "preview_mean_abs_error": self._normalize_preview_metric(preview, "mean_abs_error"),
                    "preview_saturation_ratio": self._normalize_preview_metric(preview, "saturation_ratio"),
                    "preview_temp_swing": self._normalize_preview_metric(preview, "temp_swing"),
                    "effect_outcome": s.actual_effect_label,
                    "preview_gap_level": s.preview_gap_label,
                    "feedback_usable_for_training": True,
                }
            )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(items)
        df.to_parquet(out_path, index=False)
        return len(items)

    def _run_train_script(self, *, script_rel_path: str, dataset_path: Path, artifacts_dir: Path) -> tuple[bool, str]:
        cmd = [
            sys.executable,
            str(self.repo_root / script_rel_path),
            "--data",
            str(dataset_path),
            "--artifacts-dir",
            str(artifacts_dir),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(self.repo_root))
        logs = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return proc.returncode == 0, logs[-8000:]

    def _load_json(self, path: Path) -> Optional[dict[str, Any]]:
        if not path.exists() or not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _extract_best_model_metrics(self, payload: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not isinstance(payload, dict):
            return None
        models = payload.get("models")
        if not isinstance(models, dict):
            return None
        candidates: list[tuple[str, dict[str, Any]]] = []
        for name, m in models.items():
            if isinstance(m, dict):
                candidates.append((str(name), m))
        if not candidates:
            return None
        preferred = [x for x in candidates if x[0] == "tree"] or candidates
        best = max(preferred, key=lambda x: float((x[1].get("macro_f1") or 0.0)))
        out = dict(best[1])
        out["model_variant"] = best[0]
        return out

    def _extract_class_metric(self, metrics: dict[str, Any], label: str, field: str) -> Optional[float]:
        report = metrics.get("classification_report")
        if not isinstance(report, dict):
            return None
        section = report.get(label)
        if not isinstance(section, dict):
            return None
        value = section.get(field)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _danger_misclass_rate(self, metrics: dict[str, Any], *, danger_label: str, dangerous_pred_labels: tuple[str, ...]) -> Optional[float]:
        labels = metrics.get("confusion_matrix_labels")
        matrix = metrics.get("confusion_matrix")
        if not isinstance(labels, list) or not isinstance(matrix, list):
            return None
        try:
            li = {str(k): i for i, k in enumerate(labels)}
            danger_idx = li[danger_label]
            row = matrix[danger_idx] if danger_idx < len(matrix) and isinstance(matrix[danger_idx], list) else None
            if not isinstance(row, list):
                return None
            total = sum(int(v or 0) for v in row)
            if total <= 0:
                return None
            mis = 0
            for pred in dangerous_pred_labels:
                pi = li.get(pred)
                if pi is None or pi >= len(row):
                    continue
                mis += int(row[pi] or 0)
            return float(mis) / float(total)
        except Exception:
            return None

    def _gate(
        self,
        *,
        family: FamilySpec,
        candidate_metrics: dict[str, Any],
        active_metrics: Optional[dict[str, Any]],
    ) -> tuple[bool, list[str], dict[str, Any]]:
        reasons: list[str] = []
        min_valid = max(1, int(settings.model_lifecycle_min_validation_samples))
        max_macro_reg = float(settings.model_lifecycle_max_macro_f1_regression)
        max_danger_reg = float(settings.model_lifecycle_max_danger_recall_regression)
        max_danger_misclass_reg = float(settings.model_lifecycle_max_danger_misclass_regression)
        min_improve = float(settings.model_lifecycle_min_macro_f1_improvement)
        min_first_danger = float(settings.model_lifecycle_min_first_promotion_danger_recall)

        cand_macro_f1 = float(candidate_metrics.get("macro_f1") or 0.0)
        cand_macro_recall = float(candidate_metrics.get("macro_recall") or 0.0)
        cand_valid = int(candidate_metrics.get("validation_size") or 0)
        cand_danger_recall = self._extract_class_metric(candidate_metrics, family.danger_label, "recall")
        cand_danger_f1 = self._extract_class_metric(candidate_metrics, family.danger_label, "f1-score")
        cand_danger_mis = self._danger_misclass_rate(
            candidate_metrics,
            danger_label=family.danger_label,
            dangerous_pred_labels=family.dangerous_pred_labels,
        )

        if cand_valid < min_valid:
            reasons.append(f"validation_size_too_small({cand_valid}<{min_valid})")
        if cand_danger_recall is None:
            reasons.append(f"missing_{family.danger_label}_recall")

        active_exists = active_metrics is not None
        active_macro_f1 = None
        active_danger_recall = None
        active_danger_mis = None
        if active_metrics is not None:
            active_macro_f1 = float(active_metrics.get("macro_f1") or 0.0)
            active_danger_recall = self._extract_class_metric(active_metrics, family.danger_label, "recall")
            active_danger_mis = self._danger_misclass_rate(
                active_metrics,
                danger_label=family.danger_label,
                dangerous_pred_labels=family.dangerous_pred_labels,
            )
            if cand_macro_f1 < (active_macro_f1 - max_macro_reg):
                reasons.append(
                    f"macro_f1_regression(candidate={cand_macro_f1:.4f},active={active_macro_f1:.4f},tol={max_macro_reg:.4f})"
                )
            if (
                active_danger_recall is not None
                and cand_danger_recall is not None
                and cand_danger_recall < (active_danger_recall - max_danger_reg)
            ):
                reasons.append(
                    f"{family.danger_label}_recall_regression(candidate={cand_danger_recall:.4f},active={active_danger_recall:.4f},tol={max_danger_reg:.4f})"
                )
            if (
                active_danger_mis is not None
                and cand_danger_mis is not None
                and cand_danger_mis > (active_danger_mis + max_danger_misclass_reg)
            ):
                reasons.append(
                    f"{family.danger_label}_misclass_worsened(candidate={cand_danger_mis:.4f},active={active_danger_mis:.4f},tol={max_danger_misclass_reg:.4f})"
                )
            if (
                cand_macro_f1 < (active_macro_f1 + min_improve)
                and (active_danger_recall is None or cand_danger_recall is None or cand_danger_recall <= active_danger_recall)
                and (active_danger_mis is None or cand_danger_mis is None or cand_danger_mis >= active_danger_mis)
            ):
                reasons.append("no_material_safety_or_quality_gain")
        else:
            if cand_danger_recall is not None and cand_danger_recall < min_first_danger:
                reasons.append(
                    f"{family.danger_label}_recall_below_first_promotion_min({cand_danger_recall:.4f}<{min_first_danger:.4f})"
                )

        comparison = {
            "active_exists": active_exists,
            "candidate": {
                "macro_f1": cand_macro_f1,
                "macro_recall": cand_macro_recall,
                "validation_size": cand_valid,
                "danger_label": family.danger_label,
                "danger_recall": cand_danger_recall,
                "danger_f1": cand_danger_f1,
                "danger_misclass_rate": cand_danger_mis,
            },
            "active": {
                "macro_f1": active_macro_f1,
                "danger_recall": active_danger_recall,
                "danger_misclass_rate": active_danger_mis,
            },
        }
        return len(reasons) == 0, reasons, comparison

    def _archive_and_promote(self, *, family: FamilySpec, candidate_dir: Path, run_tag: str) -> tuple[Optional[str], Optional[str]]:
        self.active_root.mkdir(parents=True, exist_ok=True)
        archive_dir = self.archive_root / family.key / run_tag
        archive_dir.mkdir(parents=True, exist_ok=True)

        active_before_dir = str(self.active_root)
        for file in self.active_root.glob(f"{family.artifact_prefix}_*"):
            if file.is_file():
                shutil.copy2(file, archive_dir / file.name)
        for file in candidate_dir.glob(f"{family.artifact_prefix}_*"):
            if file.is_file():
                shutil.copy2(file, self.active_root / file.name)
        return active_before_dir, str(archive_dir)

    def _record(
        self,
        db: Session,
        *,
        lifecycle_run_id: str,
        family: str,
        trigger_source: str,
        dry_run: bool,
        status: str,
        promoted: bool,
        reason: Optional[str],
        gate_reasons: list[str],
        training_sample_count: int,
        new_eligible_samples_since_last: int,
        recent_eligible_samples_7d: int,
        validation_size: Optional[int],
        candidate_artifact_dir: Optional[str],
        candidate_metrics_path: Optional[str],
        active_artifact_dir_before: Optional[str],
        active_metrics_path_before: Optional[str],
        archive_artifact_dir: Optional[str],
        candidate_metrics: Optional[dict[str, Any]],
        active_metrics: Optional[dict[str, Any]],
        comparison_summary: Optional[dict[str, Any]],
        started_at: datetime,
    ) -> ModelLifecycleRun:
        row = ModelLifecycleRun(
            lifecycle_run_id=lifecycle_run_id,
            model_family=family,
            trigger_source=trigger_source,
            status=status,
            promoted=promoted,
            dry_run=dry_run,
            reason=reason,
            gate_reasons=gate_reasons,
            training_sample_count=training_sample_count,
            new_eligible_samples_since_last=new_eligible_samples_since_last,
            recent_eligible_samples_7d=recent_eligible_samples_7d,
            validation_size=validation_size,
            candidate_artifact_dir=candidate_artifact_dir,
            candidate_metrics_path=candidate_metrics_path,
            active_artifact_dir_before=active_artifact_dir_before,
            active_metrics_path_before=active_metrics_path_before,
            archive_artifact_dir=archive_artifact_dir,
            candidate_metrics=candidate_metrics,
            active_metrics=active_metrics,
            comparison_summary=comparison_summary,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def run_lifecycle(self, db: Session, *, trigger_source: str = "scheduled", dry_run: bool = False) -> dict[str, Any]:
        now = datetime.utcnow()
        run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        last_completed = self._last_completed_at(db)
        last_started = self._last_started_at(db)
        cooldown = timedelta(hours=max(0, int(settings.model_lifecycle_min_hours_between_runs)))
        total_eligible = self._count_eligible_samples(db)
        recent_eligible_7d = self._count_recent_eligible_7d(db, now=now)
        new_eligible = self._count_new_since_last(db, last_completed_at=last_completed)

        skip_reason: Optional[str] = None
        if last_started is not None and now - last_started < cooldown:
            skip_reason = f"cooldown_not_elapsed(last_started={last_started.isoformat()})"
        elif new_eligible < int(settings.model_lifecycle_min_new_eligible_samples):
            skip_reason = (
                f"insufficient_new_eligible_samples({new_eligible}<{int(settings.model_lifecycle_min_new_eligible_samples)})"
            )
        elif recent_eligible_7d < int(settings.model_lifecycle_min_recent_eligible_samples_7d):
            skip_reason = (
                f"insufficient_recent_eligible_samples_7d({recent_eligible_7d}<{int(settings.model_lifecycle_min_recent_eligible_samples_7d)})"
            )

        if skip_reason:
            for family in FAMILIES:
                self._record(
                    db,
                    lifecycle_run_id=run_id,
                    family=family.key,
                    trigger_source=trigger_source,
                    dry_run=dry_run,
                    status="skipped",
                    promoted=False,
                    reason=skip_reason,
                    gate_reasons=[],
                    training_sample_count=total_eligible,
                    new_eligible_samples_since_last=new_eligible,
                    recent_eligible_samples_7d=recent_eligible_7d,
                    validation_size=None,
                    candidate_artifact_dir=None,
                    candidate_metrics_path=None,
                    active_artifact_dir_before=None,
                    active_metrics_path_before=None,
                    archive_artifact_dir=None,
                    candidate_metrics=None,
                    active_metrics=None,
                    comparison_summary=None,
                    started_at=now,
                )
            return {
                "lifecycle_run_id": run_id,
                "status": "skipped",
                "reason": skip_reason,
                "training_sample_count": total_eligible,
                "new_eligible_samples_since_last": new_eligible,
                "recent_eligible_samples_7d": recent_eligible_7d,
            }

        run_root = self.candidates_root / run_id
        dataset_path = run_root / "datasets" / "recommendation_feedback.parquet"
        training_sample_count = self._build_training_dataset(db, out_path=dataset_path)

        family_results: list[dict[str, Any]] = []
        for family in FAMILIES:
            started = datetime.utcnow()
            family_candidate_dir = run_root / family.key
            ok, logs = self._run_train_script(
                script_rel_path=family.train_script,
                dataset_path=dataset_path,
                artifacts_dir=family_candidate_dir,
            )
            if not ok:
                row = self._record(
                    db,
                    lifecycle_run_id=run_id,
                    family=family.key,
                    trigger_source=trigger_source,
                    dry_run=dry_run,
                    status="failed",
                    promoted=False,
                    reason=f"candidate_training_failed: {logs[-400:]}",
                    gate_reasons=[],
                    training_sample_count=training_sample_count,
                    new_eligible_samples_since_last=new_eligible,
                    recent_eligible_samples_7d=recent_eligible_7d,
                    validation_size=None,
                    candidate_artifact_dir=str(family_candidate_dir),
                    candidate_metrics_path=None,
                    active_artifact_dir_before=str(self.active_root),
                    active_metrics_path_before=str(self.active_root / family.metrics_file),
                    archive_artifact_dir=None,
                    candidate_metrics=None,
                    active_metrics=None,
                    comparison_summary={"train_logs_tail": logs[-2000:]},
                    started_at=started,
                )
                family_results.append({"model_family": family.key, "status": row.status, "reason": row.reason})
                continue

            candidate_metrics_payload = self._load_json(family_candidate_dir / family.metrics_file)
            candidate_best = self._extract_best_model_metrics(candidate_metrics_payload)
            active_metrics_payload = self._load_json(self.active_root / family.metrics_file)
            active_best = self._extract_best_model_metrics(active_metrics_payload)

            if candidate_best is None:
                row = self._record(
                    db,
                    lifecycle_run_id=run_id,
                    family=family.key,
                    trigger_source=trigger_source,
                    dry_run=dry_run,
                    status="failed",
                    promoted=False,
                    reason="candidate_metrics_missing_or_invalid",
                    gate_reasons=[],
                    training_sample_count=training_sample_count,
                    new_eligible_samples_since_last=new_eligible,
                    recent_eligible_samples_7d=recent_eligible_7d,
                    validation_size=None,
                    candidate_artifact_dir=str(family_candidate_dir),
                    candidate_metrics_path=str(family_candidate_dir / family.metrics_file),
                    active_artifact_dir_before=str(self.active_root),
                    active_metrics_path_before=str(self.active_root / family.metrics_file),
                    archive_artifact_dir=None,
                    candidate_metrics=candidate_metrics_payload,
                    active_metrics=active_metrics_payload,
                    comparison_summary={"train_logs_tail": logs[-2000:]},
                    started_at=started,
                )
                family_results.append({"model_family": family.key, "status": row.status, "reason": row.reason})
                continue

            passed, gate_reasons, comparison = self._gate(
                family=family,
                candidate_metrics=candidate_best,
                active_metrics=active_best,
            )
            validation_size = int(candidate_best.get("validation_size") or 0)
            promoted = False
            archive_dir = None
            active_before_dir = str(self.active_root)
            status = "rejected"
            reason = "promote_gate_rejected"
            if passed and not dry_run:
                active_before_dir, archive_dir = self._archive_and_promote(
                    family=family,
                    candidate_dir=family_candidate_dir,
                    run_tag=run_id,
                )
                status = "promoted"
                reason = "promote_gate_passed"
                promoted = True
            elif passed and dry_run:
                status = "dry_run_passed"
                reason = "promote_gate_passed_dry_run"

            row = self._record(
                db,
                lifecycle_run_id=run_id,
                family=family.key,
                trigger_source=trigger_source,
                dry_run=dry_run,
                status=status,
                promoted=promoted,
                reason=reason,
                gate_reasons=gate_reasons,
                training_sample_count=training_sample_count,
                new_eligible_samples_since_last=new_eligible,
                recent_eligible_samples_7d=recent_eligible_7d,
                validation_size=validation_size,
                candidate_artifact_dir=str(family_candidate_dir),
                candidate_metrics_path=str(family_candidate_dir / family.metrics_file),
                active_artifact_dir_before=active_before_dir,
                active_metrics_path_before=str(self.active_root / family.metrics_file),
                archive_artifact_dir=archive_dir,
                candidate_metrics=candidate_metrics_payload,
                active_metrics=active_metrics_payload,
                comparison_summary=comparison,
                started_at=started,
            )
            family_results.append(
                {
                    "model_family": family.key,
                    "status": row.status,
                    "reason": row.reason,
                    "gate_reasons": gate_reasons,
                    "promoted": promoted,
                }
            )

        return {
            "lifecycle_run_id": run_id,
            "status": "completed",
            "training_sample_count": training_sample_count,
            "new_eligible_samples_since_last": new_eligible,
            "recent_eligible_samples_7d": recent_eligible_7d,
            "families": family_results,
        }

    def list_runs(self, db: Session, *, limit: int = 20) -> list[ModelLifecycleRun]:
        return db.scalars(
            select(ModelLifecycleRun).order_by(ModelLifecycleRun.started_at.desc(), ModelLifecycleRun.id.desc()).limit(
                max(1, min(int(limit), 200))
            )
        ).all()


model_lifecycle_service = ModelLifecycleService()

