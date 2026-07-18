"""Shared contracts between ingestion, agents, API and frontend.

These models are the API contract: keep changes backward compatible or
version the endpoints. Findings without at least one citation are invalid
by construction ("no number without a source").
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

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

    @model_validator(mode="after")
    def require_locator(self) -> "Citation":
        if not self.rows and self.page is None and not self.passage:
            raise ValueError("citation must identify source rows, a page, or a passage")
        if self.rows and not self.table:
            raise ValueError("row citations require a table")
        return self


class DocumentInfo(BaseModel):
    document_id: str
    file: str
    kind: Literal["gdpdu_table", "csv", "xlsx_sheet", "docx", "pdf", "other"]
    table: str | None = None
    row_count: int | None = None


class ScoreFactor(BaseModel):
    label: str
    points: int


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


class Finding(BaseModel):
    id: str = Field(description="Stable visible id, e.g. 'F-001'")
    title: str
    description: str = Field(
        description="Short explanation of why the evidence indicates fraud risk"
    )
    likelihood: int = Field(ge=0, le=100, description="0-100 confidence that this is a real issue")
    amount_eur: float | None = Field(default=None, description="Estimated financial impact if known")
    status: Literal["finding", "needs_review"] = "finding"
    rule_ids: list[str] = Field(default_factory=list)
    rule_hit_ids: list[str] = Field(default_factory=list)
    score_factors: list[ScoreFactor] = Field(default_factory=list)
    citations: list[Citation] = Field(min_length=1)


class AgentFinding(BaseModel):
    """Finding as produced by the agent (ids are assigned server-side)."""

    title: str
    description: str = Field(
        max_length=600,
        description="At most two short sentences explaining why the evidence indicates fraud risk",
    )
    likelihood: int = Field(ge=0, le=100)
    amount_eur: float | None = None
    status: Literal["finding", "needs_review"] = "finding"
    rule_ids: list[str] = Field(default_factory=list)
    rule_hit_ids: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(min_length=1)


class CandidateDisposition(BaseModel):
    rule_hit_ids: list[str] = Field(min_length=1)
    disposition: Literal["finding", "dismissed", "needs_review"]
    reasoning: str


class AnalysisReport(BaseModel):
    """Structured output of the auditor agent run."""

    investigations: list[CandidateDisposition]
    findings: list[AgentFinding]


# ---------------------------------------------------------------------------
# Deterministic JET candidate signals
# ---------------------------------------------------------------------------


class RuleHit(BaseModel):
    """Evidence-backed investigation candidate; not yet a fraud conclusion."""

    id: str = ""
    rule_id: Literal["K1", "K2", "K3", "K4", "K5", "K6", "K7"]
    subject_type: str
    subject_id: str
    title: str
    summary: str
    risk_score: int = Field(ge=0, le=100)
    amount_eur: float | None = None
    signals: list[str] = Field(default_factory=list)
    evidence: list[Citation] = Field(min_length=1)
    counter_evidence: list[Citation] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class DetectionSummary(BaseModel):
    executed: list[str] = Field(default_factory=list)
    skipped: dict[str, str] = Field(default_factory=dict)
    hit_counts: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Global context (reusable facts, not conclusions)
# ---------------------------------------------------------------------------


class ContextItem(BaseModel):
    kind: Literal["company_fact", "policy", "terminology", "document_relationship"]
    statement: str
    citations: list[Citation] = Field(min_length=1)


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
    "detecting",
    "analyzing",
    "done",
    "error",
]

STAGE_ORDER: list[Stage] = [
    "queued",
    "extracting",
    "ingesting",
    "building_context",
    "detecting",
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
    detection: DetectionSummary | None = None
    rule_hits: list[RuleHit] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
