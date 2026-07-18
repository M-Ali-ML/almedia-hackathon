"""FastAPI app: batch upload/analysis lifecycle + AG-UI chat endpoint."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import anyio
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic_ai.ui import StateDeps  # noqa: E402
from pydantic_ai.ui.ag_ui import AGUIAdapter  # noqa: E402

from . import storage  # noqa: E402
from .agent import (  # noqa: E402
    AuditState,
    build_global_context,
    chat_agent,
    fallback_findings,
    run_analysis,
)
from .detection import run_detection, save_detection  # noqa: E402
from .ingestion import ingest_zip  # noqa: E402
from .models import BatchResult, BatchStatus, DocumentInfo, GlobalContext  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Fraud Audit Agent (MVP)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _run_pipeline(batch_id: str) -> None:
    work_dir = storage.batch_dir(batch_id)
    result = BatchResult(
        batch_id=batch_id,
        status=BatchStatus(batch_id=batch_id, stage="queued"),
    )
    logger.info("=" * 60)
    logger.info("[%s] PIPELINE START", batch_id)
    logger.info("=" * 60)
    try:
        storage.save_status(batch_id, "extracting")
        storage.save_status(batch_id, "ingesting")
        ingest = await anyio.to_thread.run_sync(
            ingest_zip, work_dir / "upload.zip", work_dir
        )
        result.documents = ingest.documents
        detail = f"{len(ingest.documents)} documents loaded"
        if ingest.warnings:
            detail += f", {len(ingest.warnings)} warnings"
            logger.warning("[%s] ingestion warnings: %s", batch_id, ingest.warnings)

        storage.save_status(batch_id, "building_context", detail)
        storage.save_result(result)

        try:
            result.global_context = await build_global_context(batch_id)
        except Exception as exc:  # noqa: BLE001 - deterministic checks can still run without LLM context
            logger.exception("[%s] global context failed; continuing with document data: %s", batch_id, exc)
            result.global_context = GlobalContext()
            (work_dir / "global_context.json").write_text(result.global_context.model_dump_json(indent=2))
        storage.save_status(batch_id, "detecting", "Running K1-K7 audit procedures")
        storage.save_result(result)

        detection = await anyio.to_thread.run_sync(
            run_detection, storage.db_path(batch_id), result.global_context
        )
        result.detection = detection.summary
        result.rule_hits = detection.hits
        save_detection(work_dir / "rule_hits.json", detection)
        detection_detail = (
            f"{len(detection.hits)} candidates from "
            f"{len(detection.summary.executed)} executed checks"
        )
        logger.info("[%s] detection complete — %s", batch_id, detection_detail)
        storage.save_status(batch_id, "analyzing", detection_detail)
        storage.save_result(result)

        try:
            result.findings = await run_analysis(batch_id, detection.hits)
        except Exception as exc:  # noqa: BLE001 - deterministic fallback keeps the batch useful
            logger.exception("[%s] agent investigation failed; using rule-hit fallback: %s", batch_id, exc)
            result.findings = fallback_findings(detection.hits)
        if not result.findings and detection.hits:
            logger.warning("[%s] agent returned no findings; preserving high-risk candidates", batch_id)
            result.findings = fallback_findings(detection.hits)
        result.status = storage.save_status(
            batch_id, "done", f"{len(result.findings)} findings"
        )
        storage.save_result(result)
        logger.info("=" * 60)
        logger.info("[%s] PIPELINE COMPLETE — %d findings", batch_id, len(result.findings))
        logger.info("=" * 60)
    except Exception as exc:  # noqa: BLE001 - surface any pipeline failure to the UI
        logger.exception("[%s] PIPELINE FAILED: %s", batch_id, exc)
        result.status = storage.save_status(batch_id, "error", error=str(exc))
        storage.save_result(result)


@app.post("/api/batches", response_model=BatchStatus)
async def create_batch(file: UploadFile, background_tasks: BackgroundTasks) -> BatchStatus:
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a .zip dossier")
    batch_id = uuid.uuid4().hex[:12]
    work_dir = storage.batch_dir(batch_id)
    work_dir.mkdir(parents=True, exist_ok=True)
    raw = await file.read()
    (work_dir / "upload.zip").write_bytes(raw)
    status = storage.save_status(batch_id, "queued")
    logger.info(
        "[%s] batch uploaded — file=%r size=%d bytes",
        batch_id,
        file.filename,
        len(raw),
    )
    background_tasks.add_task(_run_pipeline, batch_id)
    return status


@app.get("/api/batches/{batch_id}", response_model=BatchResult)
async def get_batch(batch_id: str) -> BatchResult:
    status = storage.load_status(batch_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Unknown batch")
    result = storage.load_result(batch_id) or BatchResult(batch_id=batch_id, status=status)
    result.status = status
    logger.debug("[%s] poll stage=%s detail=%s", batch_id, status.stage, status.detail)
    return result


@app.get("/api/batches/{batch_id}/documents", response_model=list[DocumentInfo])
async def get_documents(batch_id: str) -> list[DocumentInfo]:
    result = storage.load_result(batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Unknown batch")
    return result.documents


@app.post("/api/chat")
async def chat(request: Request):
    """AG-UI endpoint. The client passes {batch_id, finding} as AG-UI state."""
    logger.info("chat request received")
    return await AGUIAdapter.dispatch_request(
        request, agent=chat_agent(), deps=StateDeps(AuditState())
    )


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}
