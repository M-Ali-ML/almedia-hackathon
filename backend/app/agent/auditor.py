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

from ..ingestion import schema_overview
from ..models import AnalysisReport, Finding, GlobalContext
from .. import storage

logger = logging.getLogger(__name__)

MODEL = os.environ.get("AUDITOR_MODEL", "openai:gpt-5.1")

MAX_ROWS = 200
MAX_CHARS = 40_000


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
) -> AgentRunResult[OutputT]:
    """Run an agent while streaming progress into the server log."""
    logger.info("[%s] %s — waiting on LLM (%s)…", batch_id, process, MODEL)
    result: AgentRunResult[OutputT] | None = None
    async with agent.run_stream_events(prompt, deps=deps) as events:
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
Corroborate across independent sources before concluding anything. For every
anomaly, actively look for the innocent explanation (proper approvals, real
goods movements, documented business reasons); only report items where you
checked and could not find one. Missing real issues is bad, but flagging clean
items is also penalized — report an item only with concrete evidence.

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
approval thresholds) when designing your checks.
"""

ANALYSIS_PROMPT = """\
Analyze this dossier for indications of fraud or material misstatement.

Work systematically: inspect the schema, profile key tables (vendors,
customers, ledger postings, asset register, goods receipts, master-data
changes, approval logs, permissions, next-period postings), then run targeted
cross-document checks based on standard JET procedures and the company's own
policies from the global context. Think about segregation of duties, timing
around year-end, approval thresholds, master-data changes, and whether
recorded transactions are backed by real goods/services.

Return your findings: a short title, an audit-language description of what the
evidence shows and which innocent explanations you ruled out, a likelihood
score 0-100, the estimated EUR impact if quantifiable, and citations for every
factual claim. Order findings by evidence strength. Do not include weak
hunches without corroboration.
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


async def run_analysis(batch_id: str) -> list[Finding]:
    deps = StateDeps(AuditState(batch_id=batch_id))
    result = await _run_with_progress(
        analysis_agent(),
        ANALYSIS_PROMPT,
        batch_id=batch_id,
        process="fraud analysis",
        deps=deps,
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
    logger.info("[%s] fraud analysis complete — %d findings", batch_id, len(findings))
    return findings


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
