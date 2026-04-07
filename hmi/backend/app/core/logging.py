from __future__ import annotations

import logging
import sys
from pathlib import Path

from loguru import logger

from app.core.config import settings


_CONFIGURED = False


def _resolve_log_dir(raw: str) -> Path:
    # Resolve relative paths against backend root: hmi/backend
    backend_root = Path(__file__).resolve().parents[2]
    path = Path(raw)
    if not path.is_absolute():
        path = (backend_root / path).resolve()
    return path


def _normalize_level(value: str, default: str = "INFO") -> str:
    level = str(value or "").strip().upper()
    valid = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
    return level if level in valid else default


class InterceptHandler(logging.Handler):
    """Route stdlib logging records into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except Exception:
            level = record.levelno
        logger.bind(logger_name=record.name).opt(exception=record.exc_info).log(level, record.getMessage())


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_dir = _resolve_log_dir(settings.hmi_log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    app_log = str(log_dir / settings.hmi_log_file_name)
    error_log = str(log_dir / settings.hmi_error_log_file_name)
    access_log = str(log_dir / settings.hmi_access_log_file_name)

    root_level = _normalize_level(settings.hmi_log_level, "INFO")
    console_level = _normalize_level(settings.hmi_console_log_level, root_level)
    access_level = _normalize_level(settings.hmi_access_log_level, "INFO")

    max_bytes = max(1024 * 1024, int(settings.hmi_log_max_bytes))
    backup_count = max(1, int(settings.hmi_log_backup_count))
    log_format = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[logger_name]} | {message}"

    def is_access(record: dict) -> bool:
        return record["extra"].get("logger_name") == "uvicorn.access"

    def is_non_access(record: dict) -> bool:
        return not is_access(record)

    logger.remove()
    logger.add(
        sys.stdout,
        level=console_level,
        format=log_format,
        colorize=False,
        enqueue=False,
    )
    logger.add(
        app_log,
        level=root_level,
        format=log_format,
        rotation=max_bytes,
        retention=backup_count,
        encoding="utf-8",
        enqueue=True,
        filter=is_non_access,
    )
    logger.add(
        error_log,
        level="ERROR",
        format=log_format,
        rotation=max_bytes,
        retention=backup_count,
        encoding="utf-8",
        enqueue=True,
        filter=is_non_access,
    )
    logger.add(
        access_log,
        level=access_level,
        format=log_format,
        rotation=max_bytes,
        retention=backup_count,
        encoding="utf-8",
        enqueue=True,
        filter=is_access,
    )

    intercept = InterceptHandler()
    logging.root.handlers = [intercept]
    logging.root.setLevel(logging.NOTSET)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi", "sqlalchemy", "asyncio"):
        log = logging.getLogger(name)
        log.handlers = [intercept]
        log.propagate = False
        log.setLevel(logging.NOTSET)

    logger.bind(logger_name=__name__).info(
        "HMI logging initialized (loguru): dir={} level={} max_bytes={} backups={}",
        str(log_dir),
        root_level,
        max_bytes,
        backup_count,
    )
    _CONFIGURED = True
