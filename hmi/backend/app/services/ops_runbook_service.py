from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import OpsRunbook
from app.schemas.ops_runbook import OpsRunbookOut, OpsRunbookUpdateIn


@dataclass(frozen=True)
class RunbookDefault:
    key: str
    title: str
    section: str
    tags: list[str]
    filename: str


DEFAULT_RUNBOOKS: tuple[RunbookDefault, ...] = (
    RunbookDefault("offline_model_quality", "Offline Model Quality", "offline", ["macro-f1", "artifact", "dangerous-recall"], "offline-model-quality.md"),
    RunbookDefault("evidence_confidence", "Evidence Confidence", "summary", ["sample-size", "freshness", "confidence"], "evidence-confidence.md"),
    RunbookDefault("online_usefulness", "Online Usefulness", "online", ["ai-vs-manual", "outcomes", "evidence"], "online-usefulness.md"),
    RunbookDefault("runtime_influence", "Runtime Influence", "runtime", ["ranking", "rule_center", "influence"], "runtime-influence.md"),
    RunbookDefault("feature_drift", "Feature Drift", "drift", ["distribution-shift", "features"], "feature-drift.md"),
    RunbookDefault("runtime_reliability_fallback", "Runtime Reliability / Fallback", "runtime", ["fallback", "runtime-health"], "runtime-reliability.md"),
    RunbookDefault("label_drift", "Label Drift", "drift", ["labeling", "distribution-shift"], "label-drift.md"),
    RunbookDefault("dangerous_class_recall", "Dangerous-Class Recall", "offline", ["worse", "high", "risk"], "dangerous-class-recall.md"),
)


class OpsRunbookService:
    def _repo_root(self) -> Path:
        return Path(__file__).resolve().parents[4]

    def _default_dir(self) -> Path:
        return self._repo_root() / "hmi/backend/app/resources/runbooks/ai-ops"

    def _read_default_markdown(self, filename: str) -> str:
        path = self._default_dir() / filename
        if not path.exists() or not path.is_file():
            return "# Runbook\n\nDefault runbook content is unavailable."
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return "# Runbook\n\nDefault runbook content is unavailable."

    def _default_map(self) -> dict[str, RunbookDefault]:
        return {item.key: item for item in DEFAULT_RUNBOOKS}

    def _normalize_required_text(self, value: str, *, field_name: str) -> str:
        normalized = str(value).strip()
        if not normalized:
            raise HTTPException(status_code=400, detail=f"{field_name} must not be blank")
        return normalized

    def _normalize_tags(self, tags: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            normalized = str(tag).strip().lower()
            if not normalized or normalized in seen:
                continue
            out.append(normalized)
            seen.add(normalized)
        return out

    def _to_out(self, row: OpsRunbook) -> OpsRunbookOut:
        tags = row.tags if isinstance(row.tags, list) else []
        return OpsRunbookOut(
            key=row.key,
            title=row.title,
            section=row.section,
            tags=[str(t) for t in tags],
            markdown_body=row.markdown_body,
            is_active=bool(row.is_active),
            is_customized=bool(row.is_customized),
            version=int(row.version or 1),
            updated_by=row.updated_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def ensure_defaults_seeded(self, db: Session) -> None:
        existing = {
            str(key)
            for key in db.scalars(select(OpsRunbook.key)).all()
        }
        created = 0
        now = datetime.utcnow()
        for item in DEFAULT_RUNBOOKS:
            if item.key in existing:
                continue
            row = OpsRunbook(
                key=item.key,
                title=item.title,
                section=item.section,
                tags=item.tags,
                markdown_body=self._read_default_markdown(item.filename),
                is_active=True,
                is_customized=False,
                version=1,
                updated_by="system_seed",
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            created += 1
        if created > 0:
            db.commit()

    def list_runbooks(self, db: Session, *, include_inactive: bool = False) -> list[OpsRunbookOut]:
        self.ensure_defaults_seeded(db)
        stmt = select(OpsRunbook).order_by(OpsRunbook.section.asc(), OpsRunbook.key.asc())
        if not include_inactive:
            stmt = stmt.where(OpsRunbook.is_active.is_(True))
        rows = db.scalars(stmt).all()
        return [self._to_out(row) for row in rows]

    def get_runbook(self, db: Session, key: str) -> OpsRunbookOut:
        self.ensure_defaults_seeded(db)
        row = db.scalar(select(OpsRunbook).where(OpsRunbook.key == key))
        if row is None:
            # Fallback to repo default template even if DB row is missing.
            default = self._default_map().get(key)
            if default is None:
                raise HTTPException(status_code=404, detail="Runbook not found")
            now = datetime.utcnow()
            return OpsRunbookOut(
                key=default.key,
                title=default.title,
                section=default.section,
                tags=default.tags,
                markdown_body=self._read_default_markdown(default.filename),
                is_active=True,
                is_customized=False,
                version=1,
                updated_by="system_default",
                created_at=now,
                updated_at=now,
            )
        return self._to_out(row)

    def update_runbook(self, db: Session, key: str, payload: OpsRunbookUpdateIn, *, updated_by: str) -> OpsRunbookOut:
        self.ensure_defaults_seeded(db)
        row = db.scalar(select(OpsRunbook).where(OpsRunbook.key == key))
        if row is None:
            raise HTTPException(status_code=404, detail="Runbook not found")

        if payload.title is not None:
            row.title = self._normalize_required_text(payload.title, field_name="title")
        if payload.section is not None:
            row.section = self._normalize_required_text(payload.section, field_name="section")
        if payload.tags is not None:
            row.tags = self._normalize_tags(payload.tags)
        if payload.markdown_body is not None:
            row.markdown_body = self._normalize_required_text(payload.markdown_body, field_name="markdown_body")
        if payload.is_active is not None:
            row.is_active = bool(payload.is_active)

        row.is_customized = True
        row.version = int(row.version or 1) + 1
        row.updated_by = updated_by
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return self._to_out(row)

    def reset_to_default(self, db: Session, key: str, *, updated_by: str) -> OpsRunbookOut:
        self.ensure_defaults_seeded(db)
        row = db.scalar(select(OpsRunbook).where(OpsRunbook.key == key))
        if row is None:
            raise HTTPException(status_code=404, detail="Runbook not found")
        default = self._default_map().get(key)
        if default is None:
            raise HTTPException(status_code=404, detail="Runbook default template not found")

        row.title = default.title
        row.section = default.section
        row.tags = default.tags
        row.markdown_body = self._read_default_markdown(default.filename)
        row.is_active = True
        row.is_customized = False
        row.version = int(row.version or 1) + 1
        row.updated_by = updated_by
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return self._to_out(row)


ops_runbook_service = OpsRunbookService()
