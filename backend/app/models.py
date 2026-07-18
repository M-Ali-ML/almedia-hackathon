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


ImpactType = Literal[
    "profit_overstatement",
    "cash_misappropriation",
    "control_breach",
    "disclosure",
    "other",
]

ReviewState = Literal["pending", "accepted", "rejected"]


class Finding(BaseModel):
    id: str = Field(description="Stable visible id, e.g. 'F-001'")
    title: str
    description: str = Field(description="Free-text description of the suspected issue, audit language")
    likelihood: int = Field(ge=0, le=100, description="0-100 confidence, computed from corroboration + verifier")
    amount_eur: float | None = Field(default=None, description="Estimated financial impact if known")
    impact_type: ImpactType = Field(
        default="other", description="How the issue affects the accounts (drives the impact rollup)"
    )
    citations: list[Citation] = Field(min_length=1)
    # --- populated by the verifier pass (Phase 4) ---
    source_count: int = Field(
        default=0, description="Independent documents whose cited rows were confirmed to exist"
    )
    verified: bool = Field(default=False, description="Verifier independently confirmed the evidence")
    verification_note: str | None = Field(
        default=None, description="Second-pass verifier's audit note (why confirmed / caveats)"
    )
    # --- human-in-the-loop review (Phase 5) ---
    review_state: ReviewState = Field(default="pending")
    review_note: str | None = Field(default=None)


class AgentFinding(BaseModel):
    """Finding as produced by the agent (ids are assigned server-side)."""

    title: str
    description: str
    likelihood: int = Field(ge=0, le=100)
    amount_eur: float | None = None
    impact_type: ImpactType = Field(
        default="other",
        description=(
            "profit_overstatement (e.g. capitalized repairs, missing accrual), "
            "cash_misappropriation (funds paid out for nothing), control_breach "
            "(policy/SoD violation with no direct misstatement), disclosure "
            "(related-party/disclosure issue), or other"
        ),
    )
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


# ---------------------------------------------------------------------------
# Verifier pass (Phase 4): independent second opinion on each finding
# ---------------------------------------------------------------------------


class FindingVerification(BaseModel):
    """The verifier's independent verdict on one finding."""

    finding_id: str = Field(description="Id of the finding under review, e.g. 'F-001'")
    verdict: Literal["confirmed", "uncertain", "refuted"] = Field(
        description="confirmed = evidence re-derived; refuted = innocent explanation found"
    )
    corroborating_document_ids: list[str] = Field(
        default_factory=list,
        description="Distinct documents independently confirmed to support the finding",
    )
    note: str = Field(description="Audit-language justification for the verdict")
    innocent_explanation: str | None = Field(
        default=None, description="For refuted findings: the concrete innocent explanation found"
    )


class VerificationReport(BaseModel):
    """Structured output of the verifier agent run."""

    verifications: list[FindingVerification] = Field(default_factory=list)


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


# ---------------------------------------------------------------------------
# Review + evidence + impact (Phase 5 UX)
# ---------------------------------------------------------------------------


class ReviewUpdate(BaseModel):
    review_state: ReviewState
    review_note: str | None = None


class EvidenceRow(BaseModel):
    row_id: int
    cited: bool
    values: dict[str, str | None]


class Evidence(BaseModel):
    """Server-rendered context around a citation for the evidence viewer."""

    kind: Literal["table", "prose", "not_found"]
    document_id: str | None = None
    file: str | None = None
    table: str | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[EvidenceRow] = Field(default_factory=list)
    passages: list[dict[str, str]] = Field(default_factory=list)
    detail: str | None = None


class ImpactLine(BaseModel):
    id: str
    title: str
    impact_type: ImpactType
    amount_eur: float | None
    review_state: ReviewState


class ImpactSummary(BaseModel):
    """Financial-impact rollup.

    Headline figures cover every *active* finding (all findings except those the
    auditor rejected), so the card is never misleadingly empty. The `confirmed_*`
    figures cover only findings the auditor has explicitly accepted and grow as
    the review progresses.
    """

    reported_profit_eur: float | None = None
    reported_profit_source: Citation | None = None
    # active = not rejected (pending + accepted)
    total_exposure_eur: float = 0.0
    profit_overstatement_eur: float = 0.0
    corrected_profit_eur: float | None = None
    cash_misappropriation_eur: float = 0.0
    control_breach_count: int = 0
    # confirmed = accepted only
    confirmed_exposure_eur: float = 0.0
    confirmed_overstatement_eur: float = 0.0
    # review counts
    finding_count: int = 0
    accepted_count: int = 0
    pending_count: int = 0
    rejected_count: int = 0
    lines: list[ImpactLine] = Field(default_factory=list)
