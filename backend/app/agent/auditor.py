"""The single auditor agent of the MVP.

One general-purpose agent, two entry points:
- ``run_analysis``: structured run that produces the findings list
- ``chat_agent`` via AG-UI: conversational follow-up scoped to one finding

Both share the same read-only tools over the batch DuckDB database. The agent
is primed with generic Journal Entry Testing methodology only — never with
known scheme names, entities, or answer-key content.
"""

from __future__ import annotations

import json
import logging
import os
from functools import cache
from typing import Any

import duckdb
from pydantic import BaseModel
from pydantic_ai import Agent, AgentRunResultEvent, ModelRetry, RunContext
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartStartEvent,
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
)
from pydantic_ai.run import AgentRunResult
from pydantic_ai.ui import StateDeps
from pydantic_ai.usage import UsageLimits

from ..ingestion import schema_overview
from ..models import AnalysisReport, Finding, GlobalContext, RuledOut
from .. import storage
from ..checks import CHECKS_BY_ID, load_check_report, run_one_check

logger = logging.getLogger(__name__)

MODEL = os.environ.get("AUDITOR_MODEL", "openai:gpt-5.1")

MAX_ROWS = 200
MAX_CHARS = 40_000

# The analysis must run many focused tool rounds (the shallow ~4-call run is the
# failure mode we are fixing), so raise the request budget well above default.
ANALYSIS_REQUEST_LIMIT = int(os.environ.get("AUDITOR_REQUEST_LIMIT", "60"))


def _snip(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _log_agent_event(batch_id: str, process: str, event: object) -> None:
    """Translate pydantic-ai stream events into readable process logs."""
    if isinstance(event, PartStartEvent):
        part = event.part
        if isinstance(part, ThinkingPart):
            logger.info("[%s] %s → model thinking…", batch_id, process)
        elif isinstance(part, TextPart):
            logger.info("[%s] %s → model writing response…", batch_id, process)
        elif isinstance(part, ToolCallPart):
            logger.info(
                "[%s] %s → model requesting tool %s",
                batch_id,
                process,
                part.tool_name,
            )
        elif isinstance(part, RetryPromptPart):
            logger.warning("[%s] %s → model retry prompted", batch_id, process)
    elif isinstance(event, FunctionToolCallEvent):
        args = getattr(event.part, "args", None)
        logger.info(
            "[%s] %s → calling tool %s(%s)",
            batch_id,
            process,
            event.part.tool_name,
            _snip(str(args), 120),
        )
    elif isinstance(event, FunctionToolResultEvent):
        tool_name = getattr(event.part, "tool_name", "?")
        logger.info("[%s] %s → tool %s returned", batch_id, process, tool_name)
    elif isinstance(event, AgentRunResultEvent):
        logger.info("[%s] %s → agent run finished", batch_id, process)


async def _run_with_progress[AgentDepsT, OutputT](
    agent: Agent[AgentDepsT, OutputT],
    prompt: str,
    *,
    batch_id: str,
    process: str,
    deps: AgentDepsT | None = None,
    usage_limits: UsageLimits | None = None,
) -> AgentRunResult[OutputT]:
    """Run an agent while streaming progress into the server log."""
    logger.info("[%s] %s — waiting on LLM (%s)…", batch_id, process, MODEL)
    result: AgentRunResult[OutputT] | None = None
    kwargs: dict[str, Any] = {"deps": deps}
    if usage_limits is not None:
        kwargs["usage_limits"] = usage_limits
    async with agent.run_stream_events(prompt, **kwargs) as events:
        async for event in events:
            _log_agent_event(batch_id, process, event)
            if isinstance(event, AgentRunResultEvent):
                result = event.result
    if result is None:
        raise RuntimeError(f"{process}: agent finished without a result event")
    return result


class AuditState(BaseModel):
    """Shared AG-UI state: which batch we operate on and, for chat, which finding."""

    batch_id: str = ""
    finding: dict[str, Any] | None = None


AuditDeps = StateDeps[AuditState]


def _connect(ctx: RunContext[AuditDeps]) -> duckdb.DuckDBPyConnection:
    batch_id = ctx.deps.state.batch_id
    path = storage.db_path(batch_id)
    if not path.exists():
        raise ModelRetry(f"No database found for batch '{batch_id}'.")
    return duckdb.connect(str(path), read_only=True)


def _rows_to_json(cursor: duckdb.DuckDBPyConnection) -> str:
    columns = [d[0] for d in cursor.description]
    rows = cursor.fetchmany(MAX_ROWS + 1)
    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]
    payload = {
        "columns": columns,
        "rows": [[str(v) if v is not None else None for v in row] for row in rows],
        "truncated": truncated,
    }
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) > MAX_CHARS:
        payload["rows"] = payload["rows"][: max(1, MAX_ROWS // 10)]
        payload["truncated"] = True
        text = json.dumps(payload, ensure_ascii=False)
    return text


INSTRUCTIONS = """\
You are an experienced forensic auditor examining a German GDPdU accounting
dossier (fiscal year data of a mid-sized company, German and English content).
All files were normalized into one read-only DuckDB database.

Method — classic Journal Entry Testing: understand the population first, then
investigate who posted what, when, where, and whether controls were respected.
Corroborate across independent sources before concluding anything.

A deterministic check library has already run over this dossier and surfaced
candidate anomalies with exact table/_row_id evidence (see "Deterministic check
candidates" below). These are pre-computed leads, not conclusions — your job is
to investigate each one with SQL, corroborate it across independent sources,
and then EITHER report it as a finding OR record it as ruled_out with the
innocent explanation you found. Treat the candidates as your worklist; you may
also find issues the checks missed.

Decoy discipline: some candidates are innocent (a new vendor with four-eyes
approval and real deliveries; a large but genuine capital asset; a disclosed
related party; a documented rebate). Flagging a clean item costs points — so
rule those out explicitly rather than reporting them. But the opposite failure
is just as bad: returning few or no findings when strong, corroborated signals
exist is a FAILURE. Every check candidate that fired must appear in your output
as either a finding or a ruled_out entry — never silently dropped.

Hard rules for evidence:
- Every claim must cite the exact source: document_id, file, table and
  _row_id values (or page/paragraph ref for prose documents), plus a short
  verbatim excerpt. `_row_id` is the physical row number in the source file.
- Never invent numbers, names, or rows. Only cite rows you actually saw in
  query results. If unsure, query again.
- Amounts are EUR unless stated otherwise. Dates are DATE-typed where parsing
  succeeded; German-formatted strings elsewhere.

Company policies, terminology and document relationships extracted from the
prose documents are provided below as "Global context" — use them (e.g.
approval thresholds) when corroborating candidates.
"""

ANALYSIS_PROMPT = """\
Analyze this dossier for fraud and material misstatement, working from the
deterministic check candidates in your instructions plus your own JET procedures.

Process — do NOT stop after a shallow browse:
1. Skim the schema and the check candidates. Build a worklist from every check
   that fired.
2. For each candidate, run focused SQL against the exact entities/rows named
   (e.g. the specific vendor account, asset numbers, invoice ids). Do not settle
   for `SELECT * ... LIMIT 50`; chase the actual entity.
3. Corroborate across independent sources before concluding: for a suspected
   fake vendor, check the master-data change log (creator vs approver), the
   goods-receipt list, the permission matrix, and the ledger postings. For
   capitalized repairs, compare the asset wording against the debited account
   and whether a repair expense account exists. For cut-off, compare invoice vs
   service dates against year-end accruals actually booked. For split payments,
   confirm same vendor + same day + each under the policy limit.
4. Actively seek the innocent explanation for each candidate.

Then produce:
- findings: real issues, each with a short title, an audit-language description
  of the evidence AND which innocent explanations you ruled out, a likelihood
  0-100, the estimated EUR impact if quantifiable, and citations for every
  factual claim. Order by evidence strength.
- ruled_out: every candidate you investigated and dismissed, with the concrete
  innocent explanation and (where relevant) the related check_id.

Coverage requirement: the union of findings and ruled_out must account for
every check candidate that fired. An empty or near-empty findings list when
strongly corroborated signals exist is a failure mode, not caution.
"""


def _instructions(ctx: RunContext[AuditDeps]) -> str:
    batch_id = ctx.deps.state.batch_id
    parts = [INSTRUCTIONS]
    try:
        parts.append("Database schema:\n" + schema_overview(storage.db_path(batch_id)))
    except Exception:
        parts.append("Database schema unavailable — use the sql tool to inspect information_schema.")
    context_path = storage.batch_dir(batch_id) / "global_context.json"
    if context_path.exists():
        parts.append("Global context:\n" + context_path.read_text())
    report = load_check_report(batch_id)
    if report is not None and report.fired:
        parts.append(
            "Deterministic check candidates (pre-computed leads with exact evidence; "
            "investigate, then report or rule out each one):\n" + report.render_for_agent()
        )
    if ctx.deps.state.finding:
        parts.append(
            "The auditor is asking follow-up questions about this specific finding "
            "(verify claims against the database when asked):\n"
            + json.dumps(ctx.deps.state.finding, ensure_ascii=False)
        )
    return "\n\n".join(parts)


def _register_tools(agent: Agent) -> None:
    @agent.tool
    def run_sql(ctx: RunContext[AuditDeps], query: str) -> str:
        """Run a read-only SQL query (DuckDB dialect) against the dossier database.

        Results are capped at 200 rows — use aggregation/LIMIT for large tables.
        Always select `_row_id` when you plan to cite rows as evidence.
        """
        batch_id = ctx.deps.state.batch_id
        logger.info("[%s] tool run_sql: %s", batch_id, _snip(query))
        con = _connect(ctx)
        try:
            cursor = con.execute(query)
            payload = _rows_to_json(cursor)
            n_rows = len(json.loads(payload).get("rows", []))
            logger.info("[%s] tool run_sql → %d rows", batch_id, n_rows)
            return payload
        except duckdb.Error as exc:
            logger.warning("[%s] tool run_sql failed: %s", batch_id, exc)
            raise ModelRetry(f"SQL error: {exc}") from exc
        finally:
            con.close()

    @agent.tool
    def list_checks(ctx: RunContext[AuditDeps]) -> str:
        """List the deterministic checks and how many candidates each produced.

        These are the pre-computed leads; use run_check to get the full detail
        for one, or run_sql to investigate the cited rows directly.
        """
        batch_id = ctx.deps.state.batch_id
        report = load_check_report(batch_id)
        if report is None:
            return "No check report available for this batch."
        lines = [
            f"{r.check_id}: {len(r.hits)} candidate(s) [{r.status}] — {r.title}"
            for r in report.results
        ]
        return "\n".join(lines)

    @agent.tool
    def run_check(ctx: RunContext[AuditDeps], check_id: str) -> str:
        """Re-run one deterministic check by id and return its full result as JSON.

        Available ids come from list_checks (e.g. 'new_vendor_profile',
        'missing_goods_receipt', 'repair_vocab_in_assets', 'cutoff_unaccrued',
        'threshold_split_cluster'). Each hit carries table + _row_id evidence.
        """
        batch_id = ctx.deps.state.batch_id
        logger.info("[%s] tool run_check: %s", batch_id, check_id)
        if check_id not in CHECKS_BY_ID:
            raise ModelRetry(
                f"Unknown check '{check_id}'. Available: {', '.join(sorted(CHECKS_BY_ID))}."
            )
        con = _connect(ctx)
        try:
            result = run_one_check(con, check_id)
        finally:
            con.close()
        logger.info("[%s] tool run_check %s → %d hits", batch_id, check_id, len(result.hits))
        return result.model_dump_json()

    @agent.tool
    def read_document(ctx: RunContext[AuditDeps], file_or_document_id: str) -> str:
        """Read the extracted text of a prose document (DOCX/PDF) by file path or document_id.

        Returns passages with their refs (e.g. 'paragraph 3', 'page 1') for citations.
        """
        batch_id = ctx.deps.state.batch_id
        logger.info("[%s] tool read_document: %r", batch_id, file_or_document_id)
        con = _connect(ctx)
        try:
            cursor = con.execute(
                "SELECT document_id, file, ref, text FROM document_texts "
                "WHERE document_id = ? OR file ILIKE '%' || ? || '%' ORDER BY rowid",
                [file_or_document_id, file_or_document_id],
            )
            rows = cursor.fetchall()
            if not rows:
                logger.warning(
                    "[%s] tool read_document: no match for %r",
                    batch_id,
                    file_or_document_id,
                )
                raise ModelRetry(
                    f"No prose document matching '{file_or_document_id}'. "
                    "Check the documents table for available files."
                )
            out = [f"{r[0]} {r[1]}" for r in rows[:1]]
            out += [f"[{r[2]}] {r[3]}" for r in rows]
            text = "\n".join(out)[:MAX_CHARS]
            logger.info(
                "[%s] tool read_document → %d passages (%d chars)",
                batch_id,
                len(rows),
                len(text),
            )
            return text
        finally:
            con.close()


# Agents are built lazily so the server can boot before OPENAI_API_KEY is set.


@cache
def analysis_agent() -> Agent[AuditDeps, AnalysisReport]:
    agent: Agent[AuditDeps, AnalysisReport] = Agent(
        MODEL,
        deps_type=AuditDeps,
        output_type=AnalysisReport,
        instructions=_instructions,
        retries=3,
    )
    _register_tools(agent)

    @agent.output_validator
    def _validate_citations(ctx: RunContext[AuditDeps], report: AnalysisReport) -> AnalysisReport:
        """Reject findings citing tables that don't exist — cheap anti-hallucination net."""
        path = storage.db_path(ctx.deps.state.batch_id)
        con = duckdb.connect(str(path), read_only=True)
        try:
            tables = {
                r[0]
                for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()
            }
        finally:
            con.close()
        bad = [
            c.table
            for f in report.findings
            for c in f.citations
            if c.table and c.table not in tables
        ]
        if bad:
            raise ModelRetry(
                f"Citations reference unknown tables: {sorted(set(bad))}. Fix the citations."
            )
        return report

    return agent


@cache
def chat_agent() -> Agent[AuditDeps, str]:
    agent: Agent[AuditDeps, str] = Agent(
        MODEL,
        deps_type=AuditDeps,
        instructions=_instructions,
        retries=3,
    )
    _register_tools(agent)
    return agent


async def run_analysis(batch_id: str) -> tuple[list[Finding], list[RuledOut]]:
    deps = StateDeps(AuditState(batch_id=batch_id))
    result = await _run_with_progress(
        analysis_agent(),
        ANALYSIS_PROMPT,
        batch_id=batch_id,
        process="fraud analysis",
        deps=deps,
        usage_limits=UsageLimits(request_limit=ANALYSIS_REQUEST_LIMIT),
    )
    findings: list[Finding] = []
    for i, f in enumerate(result.output.findings, start=1):
        findings.append(
            Finding(
                id=f"F-{i:03d}",
                title=f.title,
                description=f.description,
                likelihood=f.likelihood,
                amount_eur=f.amount_eur,
                citations=f.citations,
            )
        )
        logger.info(
            "[%s] finding %s likelihood=%s amount=%s — %s",
            batch_id,
            findings[-1].id,
            f.likelihood,
            f.amount_eur,
            _snip(f.title, 80),
        )
    ruled_out = list(result.output.ruled_out)
    logger.info(
        "[%s] fraud analysis complete — %d findings, %d ruled out",
        batch_id,
        len(findings),
        len(ruled_out),
    )
    return findings, ruled_out


# ---------------------------------------------------------------------------
# Global context extraction (one cheap structured call over prose documents)
# ---------------------------------------------------------------------------

@cache
def context_agent() -> Agent[None, GlobalContext]:
    return Agent(
        MODEL,
        output_type=GlobalContext,
        instructions=(
            "You extract reusable background context from a company's audit dossier: "
            "company facts, stated policies (e.g. approval limits, materiality), important "
            "terminology, and relationships between documents. Cite the source document for "
            "each item (document_id, file, and page/paragraph ref in `passage`). "
            "Do NOT include suspicions, conclusions, or fraud assessments — facts only."
        ),
    )


async def build_global_context(batch_id: str) -> GlobalContext:
    logger.info("[%s] building global context (model=%s)", batch_id, MODEL)
    con = duckdb.connect(str(storage.db_path(batch_id)), read_only=True)
    try:
        texts = con.execute(
            "SELECT document_id, file, ref, text FROM document_texts ORDER BY document_id, rowid"
        ).fetchall()
        docs = con.execute("SELECT document_id, file, kind, table_name FROM documents").fetchall()
    finally:
        con.close()

    logger.info(
        "[%s] context inputs — %d documents, %d prose passages",
        batch_id,
        len(docs),
        len(texts),
    )
    doc_list = "\n".join(f"- {d[0]}: {d[1]} ({d[2]}{', table ' + d[3] if d[3] else ''})" for d in docs)
    passages = "\n".join(f"[{t[0]} | {t[1]} | {t[2]}] {t[3]}" for t in texts)[:100_000]
    prompt = (
        f"Documents in the dossier:\n{doc_list}\n\n"
        f"Full text of the prose documents:\n{passages or '(none)'}"
    )
    result = await _run_with_progress(
        context_agent(),
        prompt,
        batch_id=batch_id,
        process="global context",
    )
    context = result.output
    path = storage.batch_dir(batch_id) / "global_context.json"
    path.write_text(context.model_dump_json(indent=2))
    by_kind: dict[str, int] = {}
    for item in context.items:
        by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
    logger.info(
        "[%s] global context saved — %d items (%s)",
        batch_id,
        len(context.items),
        ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items())) or "none",
    )
    return context
