"""Phase 4 — verifier pass and computed corroboration scoring.

After the analysis agent produces findings, a second, independent pass:

1. Deterministically re-checks every citation against the database (the cited
   rows must actually exist) and counts how many *distinct documents* corroborate
   each finding — the multi-source score the briefing rewards (F1-class needs
   four converging sources).
2. Runs an LLM verifier that re-derives each finding from scratch with the same
   read-only tools and returns a verdict (confirmed / uncertain / refuted).
   Refuted findings are moved to the ruled-out list; the rest get a computed
   confidence that replaces the analysis agent's free likelihood guess.
"""

from __future__ import annotations

import json
import logging
import os

import duckdb
from pydantic_ai import Agent
from pydantic_ai.ui import StateDeps
from pydantic_ai.usage import UsageLimits

from .. import storage
from ..models import Finding, FindingVerification, RuledOut, VerificationReport
from .auditor import (
    ANALYSIS_REQUEST_LIMIT,
    MODEL,
    AuditDeps,
    AuditState,
    _model_settings,
    _register_tools,
    _run_with_progress,
    _snip,
)

logger = logging.getLogger(__name__)

VERIFY_ENABLED = os.environ.get("AUDITOR_VERIFY", "1").lower() not in ("0", "false", "no")

VERIFIER_INSTRUCTIONS = """\
You are a second, independent forensic auditor performing quality review of a
colleague's draft fraud findings (Cortea-style "verify before sign-off").

For each finding you are given its claim and citations. Do NOT take them on
trust. Re-derive the evidence yourself with the SQL and document tools:
- Re-query the cited tables/_row_ids and confirm the numbers, names and dates
  actually say what the finding claims.
- Independently look for the innocent explanation an honest transaction would
  have (four-eyes approval, real goods receipts, a documented investment
  request or scrapping, a disclosed related party, a booked accrual, a
  documented rebate). Use run_check and cross-table queries.
- Count how many INDEPENDENT documents genuinely corroborate the finding.

Verdicts:
- "confirmed": you re-derived the evidence and found no innocent explanation.
- "uncertain": partially supported, or you could not fully re-derive it.
- "refuted": you found a concrete innocent explanation — this is a decoy and
  must not be reported. Put the explanation in innocent_explanation.

Be decisive but evidence-bound: only refute when you can point to the specific
exonerating evidence. List the corroborating_document_ids you actually verified.
"""


def _verifier_prompt(findings: list[Finding]) -> str:
    payload = [
        {
            "finding_id": f.id,
            "title": f.title,
            "description": f.description,
            "amount_eur": f.amount_eur,
            "citations": [c.model_dump(exclude_none=True) for c in f.citations],
        }
        for f in findings
    ]
    return (
        "Review each of these draft findings independently and return a verdict "
        "for every finding_id. Re-derive the evidence with the tools before "
        "deciding.\n\nDraft findings:\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _confidence(source_count: int, verdict: str) -> int:
    """Corroboration-driven confidence, adjusted by the verifier verdict.

    More independent sources => higher confidence (the briefing's explicit
    four-source rule for the headline finding).
    """
    base = {0: 30, 1: 58, 2: 74, 3: 86}.get(source_count, 93)
    if verdict == "refuted":
        return min(base, 15)
    if verdict == "uncertain":
        return max(25, base - 18)
    return base


def _confirmed_source_count(batch_id: str, finding: Finding) -> int:
    """Distinct documents whose cited evidence actually resolves in the database."""
    con = duckdb.connect(str(storage.db_path(batch_id)), read_only=True)
    confirmed: set[str] = set()
    try:
        tables = {
            r[0]
            for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()
        }
        for c in finding.citations:
            if not c.document_id:
                continue
            if c.table and c.rows:
                if c.table not in tables:
                    continue
                placeholders = ",".join("?" for _ in c.rows)
                try:
                    n = con.execute(
                        f'SELECT count(*) FROM "{c.table}" WHERE _row_id IN ({placeholders})',
                        list(c.rows),
                    ).fetchone()[0]
                except duckdb.Error:
                    continue
                if n and n > 0:
                    confirmed.add(c.document_id)
            elif c.passage or c.page is not None:
                exists = con.execute(
                    "SELECT count(*) FROM document_texts WHERE document_id = ?",
                    [c.document_id],
                ).fetchone()[0]
                if exists:
                    confirmed.add(c.document_id)
    finally:
        con.close()
    return len(confirmed)


def _verifier_agent() -> Agent[AuditDeps, VerificationReport]:
    agent: Agent[AuditDeps, VerificationReport] = Agent(
        MODEL,
        deps_type=AuditDeps,
        output_type=VerificationReport,
        instructions=VERIFIER_INSTRUCTIONS,
        retries=3,
        model_settings=_model_settings(),
    )
    _register_tools(agent)
    return agent


async def run_verification(
    batch_id: str, findings: list[Finding], ruled_out: list[RuledOut]
) -> tuple[list[Finding], list[RuledOut]]:
    """Verify findings, compute corroboration confidence, move refuted to ruled_out."""
    if not findings:
        return findings, ruled_out
    if not VERIFY_ENABLED:
        for f in findings:
            f.source_count = _confirmed_source_count(batch_id, f)
        return findings, ruled_out

    deps = StateDeps(AuditState(batch_id=batch_id))
    result = await _run_with_progress(
        _verifier_agent(),
        _verifier_prompt(findings),
        batch_id=batch_id,
        process="verification",
        deps=deps,
        usage_limits=UsageLimits(request_limit=ANALYSIS_REQUEST_LIMIT),
    )
    by_id: dict[str, FindingVerification] = {v.finding_id: v for v in result.output.verifications}

    kept: list[Finding] = []
    new_ruled_out = list(ruled_out)
    for f in findings:
        source_count = _confirmed_source_count(batch_id, f)
        f.source_count = source_count
        verdict = by_id[f.id].verdict if f.id in by_id else "uncertain"
        note = by_id[f.id].note if f.id in by_id else "Verifier did not return a verdict."
        f.likelihood = _confidence(source_count, verdict)
        f.verified = verdict == "confirmed"
        f.verification_note = note

        if verdict == "refuted":
            v = by_id[f.id]
            new_ruled_out.append(
                RuledOut(
                    title=f.title,
                    reason=v.innocent_explanation or v.note,
                    citations=f.citations,
                )
            )
            logger.info("[%s] verifier REFUTED %s — %s", batch_id, f.id, _snip(f.title, 70))
            continue
        kept.append(f)
        logger.info(
            "[%s] verifier %s %s sources=%d conf=%d — %s",
            batch_id,
            f.id,
            verdict,
            source_count,
            f.likelihood,
            _snip(f.title, 60),
        )

    kept.sort(key=lambda f: f.likelihood, reverse=True)
    logger.info(
        "[%s] verification complete — %d confirmed/kept, %d refuted",
        batch_id,
        len(kept),
        len(findings) - len(kept),
    )
    return kept, new_ruled_out
