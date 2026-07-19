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
from fastapi.responses import FileResponse  # noqa: E402
from pydantic_ai.ui import StateDeps  # noqa: E402
from pydantic_ai.ui.ag_ui import AGUIAdapter  # noqa: E402

from . import evidence as evidence_mod  # noqa: E402
from . import storage  # noqa: E402
from .agent import (  # noqa: E402
    AuditState,
    build_global_context,
    chat_agent,
    run_analysis,
    run_verification,
)
from .checks import run_checks_for_batch  # noqa: E402
from .ingestion import ingest_zip  # noqa: E402
from .models import (  # noqa: E402
    BatchResult,
    BatchStatus,
    DocumentInfo,
    Evidence,
    Finding,
    ImpactSummary,
    ReviewUpdate,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AudiTrace")

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

        checks = await anyio.to_thread.run_sync(run_checks_for_batch, batch_id)
        detail += f", {checks.total_hits} check hits"

        storage.save_status(batch_id, "building_context", detail)
        storage.save_result(result)

        result.global_context = await build_global_context(batch_id)
        storage.save_status(batch_id, "analyzing", detail)
        storage.save_result(result)

        findings, ruled_out = await run_analysis(batch_id)
        storage.save_status(batch_id, "analyzing", "verifying findings")
        result.findings, result.ruled_out = await run_verification(
            batch_id, findings, ruled_out
        )
        result.status = storage.save_status(
            batch_id,
            "done",
            f"{len(result.findings)} findings, {len(result.ruled_out)} ruled out",
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


@app.get("/api/batches/{batch_id}/documents/{document_id}/file")
async def get_document_file(batch_id: str, document_id: str) -> FileResponse:
    """Open the original uploaded file behind a citation."""
    result = storage.load_result(batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Unknown batch")
    document = next((doc for doc in result.documents if doc.document_id == document_id), None)
    if document is None:
        raise HTTPException(status_code=404, detail="Unknown document")
    extract_dir = (storage.batch_dir(batch_id) / "extracted").resolve()
    path = (extract_dir / document.file).resolve()
    if not path.is_relative_to(extract_dir) or not path.is_file():
        raise HTTPException(status_code=404, detail="Source file not found")
    return FileResponse(path)


@app.post("/api/batches/{batch_id}/findings/{finding_id}/review", response_model=Finding)
async def review_finding(batch_id: str, finding_id: str, update: ReviewUpdate) -> Finding:
    """Auditor accept / reject / annotate a finding (human-in-the-loop)."""
    finding = storage.update_finding_review(
        batch_id, finding_id, update.review_state, update.review_note
    )
    if finding is None:
        raise HTTPException(status_code=404, detail="Unknown batch or finding")
    return finding


@app.get("/api/batches/{batch_id}/evidence", response_model=Evidence)
async def get_evidence(
    batch_id: str,
    document_id: str | None = None,
    table: str | None = None,
    rows: str | None = None,
    page: int | None = None,
) -> Evidence:
    """Server-rendered context behind a citation (table slice or prose passages)."""
    row_ids = [int(r) for r in rows.split(",") if r.strip()] if rows else None
    return evidence_mod.build_evidence(
        batch_id, document_id=document_id, table=table, rows=row_ids, page=page
    )


@app.get("/api/batches/{batch_id}/impact", response_model=ImpactSummary)
async def get_impact(batch_id: str) -> ImpactSummary:
    """Reported vs. corrected profit rollup driven by accepted findings."""
    if storage.load_status(batch_id) is None:
        raise HTTPException(status_code=404, detail="Unknown batch")
    return evidence_mod.build_impact(batch_id)


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
