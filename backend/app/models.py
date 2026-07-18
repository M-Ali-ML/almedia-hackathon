"""Shared contracts between ingestion, agents, API and frontend.

These models are the API contract: keep changes backward compatible or
version the endpoints. Findings without at least one citation are invalid
by construction ("no number without a source").
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Provenance / citations
# ---------------------------------------------------------------------------


class Citation(BaseModel):
    """A pointer to the exact evidence behind a claim.

    Exactly one of the locator groups is expected to be set depending on the
    source kind: `rows` for tabular sources, `sheet`+`rows` for spreadsheets,
    `page` or `passage` for prose documents.
    """

    document_id: str
    file: str = Field(description="Path of the source file inside the dossier zip")
    table: str | None = Field(default=None, description="DuckDB table name, for tabular sources")
    rows: list[int] | None = Field(
        default=None, description="_row_id values (1-based data row numbers in the source file)"
    )
    sheet: str | None = None
    page: int | None = None
    passage: str | None = Field(default=None, description="Reference like 'paragraph 12'")
    excerpt: str | None = Field(default=None, description="Short verbatim excerpt of the evidence")


class DocumentInfo(BaseModel):
    document_id: str
    file: str
    kind: Literal["gdpdu_table", "csv", "xlsx_sheet", "docx", "pdf", "other"]
    table: str | None = None
    row_count: int | None = None


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


class Finding(BaseModel):
    id: str = Field(description="Stable visible id, e.g. 'F-001'")
    title: str
    description: str = Field(description="Free-text description of the suspected issue, audit language")
    likelihood: int = Field(ge=0, le=100, description="0-100 confidence that this is a real issue")
    amount_eur: float | None = Field(default=None, description="Estimated financial impact if known")
    citations: list[Citation] = Field(min_length=1)


class AgentFinding(BaseModel):
    """Finding as produced by the agent (ids are assigned server-side)."""

    title: str
    description: str
    likelihood: int = Field(ge=0, le=100)
    amount_eur: float | None = None
    citations: list[Citation] = Field(min_length=1)


class RuledOut(BaseModel):
    """An anomaly the agent investigated and dismissed as an innocent explanation.

    Recording these is scored positively (it demonstrates decoy discipline) and
    prevents the "silently emit nothing" escape hatch: every deterministic check
    that fired must end up either as a Finding or as a RuledOut entry.
    """

    title: str = Field(description="The candidate/anomaly that was checked")
    reason: str = Field(description="Why it is clean, in audit language")
    check_id: str | None = Field(default=None, description="Related deterministic check, if any")
    citations: list[Citation] = Field(default_factory=list)


class AnalysisReport(BaseModel):
    """Structured output of the auditor agent run."""

    findings: list[AgentFinding]
    ruled_out: list[RuledOut] = Field(
        default_factory=list,
        description="Anomalies checked and dismissed with the innocent explanation found",
    )


# ---------------------------------------------------------------------------
# Global context (reusable facts, not conclusions)
# ---------------------------------------------------------------------------


class ContextItem(BaseModel):
    kind: Literal["company_fact", "policy", "terminology", "document_relationship"]
    statement: str
    citations: list[Citation] = Field(default_factory=list)


class GlobalContext(BaseModel):
    items: list[ContextItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline progress / batch lifecycle
# ---------------------------------------------------------------------------

Stage = Literal[
    "queued",
    "extracting",
    "ingesting",
    "building_context",
    "analyzing",
    "done",
    "error",
]

STAGE_ORDER: list[Stage] = [
    "queued",
    "extracting",
    "ingesting",
    "building_context",
    "analyzing",
    "done",
]


class BatchStatus(BaseModel):
    batch_id: str
    stage: Stage
    detail: str | None = None
    error: str | None = None


class BatchResult(BaseModel):
    batch_id: str
    status: BatchStatus
    documents: list[DocumentInfo] = Field(default_factory=list)
    global_context: GlobalContext | None = None
    findings: list[Finding] = Field(default_factory=list)
    ruled_out: list[RuledOut] = Field(default_factory=list)
