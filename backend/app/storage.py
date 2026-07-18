"""Filesystem layout for uploaded batches. One directory per batch:

    backend/data/batches/{batch_id}/
        upload.zip          original upload
        extracted/          unzipped dossier
        dossier.duckdb      normalized store
        global_context.json reusable cited dossier facts
        rule_hits.json      deterministic K1-K7 candidates
        status.json         BatchStatus
        result.json         BatchResult (documents, context, findings)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import BatchResult, BatchStatus, Stage

logger = logging.getLogger(__name__)

BATCHES_DIR = Path(__file__).resolve().parent.parent / "data" / "batches"

STAGE_LABELS: dict[Stage, str] = {
    "queued": "queued — waiting to start",
    "extracting": "extracting ZIP",
    "ingesting": "ingesting files into DuckDB",
    "building_context": "building global context (LLM)",
    "analyzing": "running fraud analysis agent (LLM)",
    "done": "done",
    "error": "failed",
}


def batch_dir(batch_id: str) -> Path:
    return BATCHES_DIR / batch_id


def db_path(batch_id: str) -> Path:
    return batch_dir(batch_id) / "dossier.duckdb"


def save_status(batch_id: str, stage: Stage, detail: str | None = None, error: str | None = None) -> BatchStatus:
    status = BatchStatus(batch_id=batch_id, stage=stage, detail=detail, error=error)
    path = batch_dir(batch_id) / "status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(status.model_dump_json(indent=2))
    label = STAGE_LABELS.get(stage, stage)
    extra = f" — {detail}" if detail else ""
    if error:
        extra = f" — {error}"
    logger.info("[%s] PROCESS: %s%s", batch_id, label, extra)
    return status


def load_status(batch_id: str) -> BatchStatus | None:
    path = batch_dir(batch_id) / "status.json"
    if not path.exists():
        return None
    return BatchStatus.model_validate_json(path.read_text())


def save_result(result: BatchResult) -> None:
    path = batch_dir(result.batch_id) / "result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(indent=2))


def load_result(batch_id: str) -> BatchResult | None:
    path = batch_dir(batch_id) / "result.json"
    if not path.exists():
        return None
    return BatchResult.model_validate_json(path.read_text())


def load_result_dict(batch_id: str) -> dict | None:
    path = batch_dir(batch_id) / "result.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
