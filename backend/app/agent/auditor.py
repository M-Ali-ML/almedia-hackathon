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
import re
from functools import cache
from typing import Any

import duckdb
from pydantic import BaseModel, Field
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
from ..models import AnalysisReport, Citation, Finding, GlobalContext, RuleHit, ScoreFactor
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
    rule_hits: list[dict[str, Any]] = Field(default_factory=list)


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
Investigate every supplied K1-K7 rule hit. These are deterministic candidates,
not fraud conclusions.

For every rule hit, verify its cited evidence, inspect relevant surrounding
records, search for counter-evidence and innocent explanations, and return one
explicit disposition: finding, dismissed, or needs_review. Do not omit a rule
hit. Merge related hits into one finding when they concern the same vendor,
journal, transaction cluster, asset population, or accounting issue.

Every finding must list the contributing rule_hit_ids and K1-K7 rule_ids. Give
an audit-language description of at most two short sentences explaining why
the pattern is suspicious, likelihood 0-100, EUR impact when quantifiable, and
exact citations for all factual claims. Put evidence details in citations, not
the description. Never create a finding whose conclusion is that no fraud was
found. Empty findings are acceptable only when every rule hit has an
evidence-based dismissal; do not return an empty investigation list when
candidates were supplied.
"""


_BLOCKED_SQL = re.compile(
    r"\b(insert|update|delete|merge|create|alter|drop|truncate|copy|attach|detach|"
    r"install|load|export|import|pragma|call|read_csv|read_json|read_parquet|read_text|"
    r"csv_scan|parquet_scan|sqlite_scan|postgres_scan|glob|httpfs)\b",
    re.IGNORECASE,
)


def _validate_read_only_sql(query: str) -> str:
    stripped = query.strip()
    if ";" in stripped.rstrip(";"):
        raise ModelRetry("Only one SQL statement is allowed.")
    stripped = stripped.rstrip(";").strip()
    if not re.match(r"^(select|with)\b", stripped, re.IGNORECASE):
        raise ModelRetry("Only SELECT or WITH queries are allowed.")
    if _BLOCKED_SQL.search(stripped):
        raise ModelRetry("The query uses a blocked statement or external-read function.")
    return stripped


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
        rule_hit_ids = set(ctx.deps.state.finding.get("rule_hit_ids", []))
        rule_hits_path = storage.batch_dir(batch_id) / "rule_hits.json"
        if rule_hit_ids and rule_hits_path.exists():
            payload = json.loads(rule_hits_path.read_text())
            related = [h for h in payload.get("hits", []) if h.get("id") in rule_hit_ids]
            parts.append("Underlying deterministic rule hits:\n" + json.dumps(related, ensure_ascii=False))
    elif ctx.deps.state.rule_hits:
        parts.append(
            "Deterministic K1-K7 rule hits to investigate:\n"
            + json.dumps(ctx.deps.state.rule_hits, ensure_ascii=False)
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
            cursor = con.execute(_validate_read_only_sql(query))
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
        """Require candidate dispositions and verify exact source locations."""
        expected_hits = {str(h.get("id")) for h in ctx.deps.state.rule_hits if h.get("id")}
        disposed_hits = {hit_id for item in report.investigations for hit_id in item.rule_hit_ids}
        missing = expected_hits - disposed_hits
        unknown = disposed_hits - expected_hits
        if missing or unknown:
            raise ModelRetry(
                f"Investigation coverage is invalid. Missing rule hits: {sorted(missing)}; "
                f"unknown rule hits: {sorted(unknown)}."
            )
        expected_rules = {str(h.get("rule_id")) for h in ctx.deps.state.rule_hits}
        for finding in report.findings:
            if expected_hits and not finding.rule_hit_ids:
                raise ModelRetry("Every finding must list its contributing rule_hit_ids.")
            if not set(finding.rule_hit_ids).issubset(expected_hits):
                raise ModelRetry("A finding references an unknown rule_hit_id.")
            if expected_rules and (
                not finding.rule_ids or not set(finding.rule_ids).issubset(expected_rules)
            ):
                raise ModelRetry("Every finding must list valid contributing K1-K7 rule_ids.")

        path = storage.db_path(ctx.deps.state.batch_id)
        con = duckdb.connect(str(path), read_only=True)
        try:
            problems = [
                problem
                for finding in report.findings
                for citation in finding.citations
                for problem in _citation_problems(con, citation)
            ]
        finally:
            con.close()
        if problems:
            raise ModelRetry("Invalid citations: " + "; ".join(problems[:10]))
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


def _score_rule_hits(rule_hits: list[RuleHit]) -> tuple[int, list[ScoreFactor]]:
    """Turn deterministic evidence into an auditable evidence-strength score."""
    strongest = max(rule_hits, key=lambda hit: hit.risk_score)
    distinct_rules = {hit.rule_id for hit in rule_hits}
    evidence_documents = {c.document_id for hit in rule_hits for c in hit.evidence}
    counter_documents = {c.document_id for hit in rule_hits for c in hit.counter_evidence}
    corroboration_bonus = min(max(len(distinct_rules) - 1, 0) * 3, 6)
    source_bonus = min(max(len(evidence_documents) - 1, 0) * 2, 6)
    counter_penalty = min(len(counter_documents) * 3, 9)
    raw_score = strongest.risk_score + corroboration_bonus + source_bonus - counter_penalty
    score = max(0, min(raw_score, 100))
    factors = [ScoreFactor(label=f"Strongest detector ({strongest.rule_id})", points=strongest.risk_score)]
    if corroboration_bonus:
        factors.append(
            ScoreFactor(
                label=f"Corroboration from {len(distinct_rules)} independent rules",
                points=corroboration_bonus,
            )
        )
    if source_bonus:
        factors.append(
            ScoreFactor(
                label=f"Evidence across {len(evidence_documents)} source documents",
                points=source_bonus,
            )
        )
    if counter_penalty:
        factors.append(
            ScoreFactor(
                label=f"Counter-evidence in {len(counter_documents)} source documents",
                points=-counter_penalty,
            )
        )
    if raw_score > 100:
        factors.append(ScoreFactor(label="Score capped at 100", points=100 - raw_score))
    return score, factors


async def run_analysis(batch_id: str, rule_hits: list[RuleHit]) -> list[Finding]:
    deps = StateDeps(
        AuditState(batch_id=batch_id, rule_hits=[h.model_dump(mode="json") for h in rule_hits])
    )
    result = await _run_with_progress(
        analysis_agent(),
        ANALYSIS_PROMPT,
        batch_id=batch_id,
        process="fraud analysis",
        deps=deps,
    )
    findings: list[Finding] = []
    hits_by_id = {hit.id: hit for hit in rule_hits}
    for i, f in enumerate(result.output.findings, start=1):
        contributing_hits = [hits_by_id[hit_id] for hit_id in f.rule_hit_ids]
        score, score_factors = _score_rule_hits(contributing_hits)
        findings.append(
            Finding(
                id=f"F-{i:03d}",
                title=f.title,
                description=f.description,
                likelihood=score,
                amount_eur=f.amount_eur,
                status=f.status,
                rule_ids=f.rule_ids,
                rule_hit_ids=f.rule_hit_ids,
                score_factors=score_factors,
                citations=f.citations,
            )
        )
        logger.info(
            "[%s] finding %s likelihood=%s amount=%s — %s",
            batch_id,
            findings[-1].id,
            findings[-1].likelihood,
            f.amount_eur,
            _snip(f.title, 80),
        )
    logger.info("[%s] fraud analysis complete — %d findings", batch_id, len(findings))
    return findings


def _citation_problems(con: duckdb.DuckDBPyConnection, citation: Citation) -> list[str]:
    """Return human-readable provenance mismatches for one citation."""
    problems: list[str] = []
    if citation.table and citation.rows:
        document = con.execute(
            "SELECT 1 FROM documents WHERE document_id = ? AND file = ? AND table_name = ? LIMIT 1",
            [citation.document_id, citation.file, citation.table],
        ).fetchone()
        if not document:
            return [f"{citation.table}: document_id/file do not match table metadata"]
        tables = {
            r[0]
            for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()
        }
        if citation.table not in tables:
            return [f"unknown table {citation.table}"]
        quoted = citation.table.replace('"', '""')
        placeholders = ",".join("?" for _ in citation.rows)
        cursor = con.execute(
            f'SELECT * FROM "{quoted}" WHERE _row_id IN ({placeholders})', citation.rows
        )
        rows = cursor.fetchall()
        if len(rows) != len(set(citation.rows)):
            problems.append(f"{citation.table}: one or more cited rows do not exist")
        if citation.excerpt and rows:
            population = "\n".join(" | ".join(str(v) for v in row if v is not None) for row in rows)
            if citation.excerpt.casefold() not in population.casefold():
                problems.append(f"{citation.table}: excerpt is not present in cited rows")
        return problems

    ref = citation.passage or (f"page {citation.page}" if citation.page is not None else None)
    if ref:
        row = con.execute(
            "SELECT text FROM document_texts WHERE document_id = ? AND file = ? AND ref = ? LIMIT 1",
            [citation.document_id, citation.file, ref],
        ).fetchone()
        if not row:
            return [f"{citation.file}: cited passage {ref!r} does not exist"]
        if citation.excerpt and citation.excerpt.casefold() not in str(row[0]).casefold():
            problems.append(f"{citation.file}: excerpt is not present in cited passage")
        return problems
    return [f"{citation.file}: citation has no verifiable locator"]


def fallback_findings(rule_hits: list[RuleHit], minimum_score: int = 75) -> list[Finding]:
    """Keep strong deterministic signals visible if model investigation fails or returns nothing."""
    groups: dict[tuple[str, str], list[RuleHit]] = {}
    for hit in rule_hits:
        if hit.risk_score >= minimum_score:
            groups.setdefault((hit.subject_type, hit.subject_id), []).append(hit)
    findings: list[Finding] = []
    for i, hits in enumerate(groups.values(), start=1):
        citations: list[Citation] = []
        seen: set[tuple] = set()
        for hit in hits:
            for citation in hit.evidence:
                key = (
                    citation.document_id,
                    citation.table,
                    tuple(citation.rows or []),
                    citation.page,
                    citation.passage,
                )
                if key not in seen:
                    seen.add(key)
                    citations.append(citation)
        primary = max(hits, key=lambda h: h.risk_score)
        score, score_factors = _score_rule_hits(hits)
        findings.append(
            Finding(
                id=f"F-{i:03d}",
                title=primary.title,
                description=" ".join(hit.summary for hit in hits),
                likelihood=score,
                amount_eur=max(
                    (hit.amount_eur for hit in hits if hit.amount_eur is not None), default=None
                ),
                status="needs_review",
                rule_ids=sorted({hit.rule_id for hit in hits}),
                rule_hit_ids=[hit.id for hit in hits],
                score_factors=score_factors,
                citations=citations,
            )
        )
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
