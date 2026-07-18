"""Contracts for the deterministic check library.

Checks emit *candidates with evidence*, never verdicts: deciding whether a hit
is fraud (vs. an innocent explanation) stays with the agent / verifier layer.
Every hit carries real `_row_id` values so downstream findings can cite it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class CheckHit(BaseModel):
    """One candidate anomaly surfaced by a check."""

    entity: str | None = Field(
        default=None, description="Main entity, e.g. vendor account, asset number, user id"
    )
    summary: str = Field(description="One-line human-readable description of the candidate")
    table: str | None = Field(default=None, description="DuckDB table the row_ids refer to")
    row_ids: list[int] = Field(default_factory=list, description="_row_id values backing this hit")
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Computed context (amounts, dates, counts, corroborating facts)",
    )


class CheckResult(BaseModel):
    check_id: str
    title: str
    description: str = Field(description="What the check tests, in generic audit terms")
    status: Literal["ok", "no_data", "error"] = "ok"
    hits: list[CheckHit] = Field(default_factory=list)
    notes: list[str] = Field(
        default_factory=list,
        description="Resolved tables, thresholds/parameters used, caveats, truncation notices",
    )


class CheckReport(BaseModel):
    batch_id: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    parameters: dict[str, Any] = Field(default_factory=dict)
    results: list[CheckResult] = Field(default_factory=list)

    @property
    def total_hits(self) -> int:
        return sum(len(r.hits) for r in self.results)

    @property
    def fired(self) -> list[CheckResult]:
        """Checks that produced at least one candidate."""
        return [r for r in self.results if r.hits]

    def render_for_agent(self, max_hits_per_check: int = 12) -> str:
        """Compact, prompt-ready view of the candidates for the analysis agent.

        Deterministic and derived purely from the dossier — safe to inject into
        prompts (it contains no answer-key content).
        """
        lines: list[str] = []
        for result in self.results:
            if not result.hits:
                header = f"- {result.check_id}: no candidates"
                if result.status != "ok":
                    header += f" ({result.status})"
                lines.append(header)
                continue
            lines.append(f"- {result.check_id} — {result.title} [{len(result.hits)} candidate(s)]")
            for note in result.notes:
                lines.append(f"    context: {note}")
            for hit in result.hits[:max_hits_per_check]:
                loc = ""
                if hit.table and hit.row_ids:
                    shown = ", ".join(str(r) for r in hit.row_ids[:12])
                    more = "…" if len(hit.row_ids) > 12 else ""
                    loc = f"  [{hit.table} _row_id {shown}{more}]"
                lines.append(f"    * {hit.summary}{loc}")
            if len(result.hits) > max_hits_per_check:
                lines.append(f"    * … {len(result.hits) - max_hits_per_check} more candidate(s)")
        return "\n".join(lines)
