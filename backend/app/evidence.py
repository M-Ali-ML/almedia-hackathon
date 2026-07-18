"""Evidence viewer + financial-impact rollup (Phase 5).

Server-side rendering of the exact context behind a citation (table slice around
the cited `_row_id`s, or the prose passages of a document) and a reported-vs-
corrected profit rollup driven by the auditor's accepted findings.
"""

from __future__ import annotations

import re

import duckdb

from . import storage
from .models import (
    Citation,
    Evidence,
    EvidenceRow,
    ImpactLine,
    ImpactSummary,
)

ROW_WINDOW = 3  # neighbouring rows shown around each cited row for context


def _connect(batch_id: str) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(storage.db_path(batch_id)), read_only=True)


def _file_for_table(con: duckdb.DuckDBPyConnection, table: str) -> str | None:
    row = con.execute(
        "SELECT file FROM documents WHERE table_name = ? LIMIT 1", [table]
    ).fetchone()
    return row[0] if row else None


def build_evidence(
    batch_id: str,
    *,
    document_id: str | None = None,
    table: str | None = None,
    rows: list[int] | None = None,
    page: int | None = None,
) -> Evidence:
    if not storage.db_path(batch_id).exists():
        return Evidence(kind="not_found", detail="No database for this batch.")
    con = _connect(batch_id)
    try:
        if table and rows:
            return _table_evidence(con, table, rows, document_id)
        if document_id or page is not None:
            return _prose_evidence(con, document_id, page)
        return Evidence(kind="not_found", detail="Provide table+rows or a document_id.")
    finally:
        con.close()


def _table_evidence(
    con: duckdb.DuckDBPyConnection, table: str, rows: list[int], document_id: str | None
) -> Evidence:
    exists = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchone()[0]
    if not exists:
        return Evidence(kind="not_found", detail=f"Unknown table '{table}'.")
    columns = [
        r[0]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ? "
            "ORDER BY ordinal_position",
            [table],
        ).fetchall()
    ]
    cited = set(rows)
    lo, hi = min(rows) - ROW_WINDOW, max(rows) + ROW_WINDOW
    data = con.execute(
        f'SELECT * FROM "{table}" WHERE _row_id BETWEEN ? AND ? ORDER BY _row_id', [lo, hi]
    ).fetchall()
    out_rows: list[EvidenceRow] = []
    for record in data:
        values = {col: (str(v) if v is not None else None) for col, v in zip(columns, record)}
        row_id = int(values.get("_row_id") or record[0])
        out_rows.append(EvidenceRow(row_id=row_id, cited=row_id in cited, values=values))
    return Evidence(
        kind="table",
        document_id=document_id,
        file=_file_for_table(con, table),
        table=table,
        columns=columns,
        rows=out_rows,
    )


def _prose_evidence(
    con: duckdb.DuckDBPyConnection, document_id: str | None, page: int | None
) -> Evidence:
    where = "document_id = ?" if document_id else "TRUE"
    params: list[object] = [document_id] if document_id else []
    records = con.execute(
        f"SELECT document_id, file, ref, text FROM document_texts WHERE {where} ORDER BY rowid",
        params,
    ).fetchall()
    if not records:
        return Evidence(kind="not_found", detail="No prose passages for that document.")
    if page is not None:
        page_rows = [r for r in records if f"page {page}" in (r[2] or "")]
        records = page_rows or records
    passages = [{"ref": r[2] or "", "text": r[3] or ""} for r in records]
    return Evidence(
        kind="prose",
        document_id=records[0][0],
        file=records[0][1],
        passages=passages,
    )


# ---------------------------------------------------------------------------
# Impact rollup
# ---------------------------------------------------------------------------

_PROFIT_RE = re.compile(
    r"Jahres(?:ü|ue|u)berschuss[^\d\-]*(-?\d{1,3}(?:\.\d{3})*(?:,\d{2})?)",
    re.IGNORECASE,
)


def _parse_de_number(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))


def _reported_profit(con: duckdb.DuckDBPyConnection) -> tuple[float | None, Citation | None]:
    records = con.execute(
        "SELECT document_id, file, ref, text FROM document_texts"
    ).fetchall()
    for document_id, file, ref, text in records:
        match = _PROFIT_RE.search(text or "")
        if match:
            try:
                value = _parse_de_number(match.group(1))
            except ValueError:
                continue
            excerpt = re.sub(r"\s+", " ", match.group(0)).strip()
            return value, Citation(
                document_id=document_id, file=file, passage=ref, excerpt=excerpt
            )
    return None, None


def build_impact(batch_id: str) -> ImpactSummary:
    result = storage.load_result(batch_id)
    findings = result.findings if result else []

    reported, source = None, None
    if storage.db_path(batch_id).exists():
        con = _connect(batch_id)
        try:
            reported, source = _reported_profit(con)
        finally:
            con.close()

    accepted = [f for f in findings if f.review_state == "accepted"]
    overstatement = sum(
        f.amount_eur or 0.0 for f in accepted if f.impact_type == "profit_overstatement"
    )
    cash = sum(f.amount_eur or 0.0 for f in accepted if f.impact_type == "cash_misappropriation")
    control = sum(1 for f in accepted if f.impact_type == "control_breach")

    summary = ImpactSummary(
        reported_profit_eur=reported,
        reported_profit_source=source,
        profit_overstatement_eur=overstatement,
        corrected_profit_eur=(reported - overstatement) if reported is not None else None,
        cash_misappropriation_eur=cash,
        control_breach_count=control,
        accepted_count=len(accepted),
        pending_count=sum(1 for f in findings if f.review_state == "pending"),
        total_flagged_eur=sum(f.amount_eur or 0.0 for f in findings),
        lines=[
            ImpactLine(
                id=f.id,
                title=f.title,
                impact_type=f.impact_type,
                amount_eur=f.amount_eur,
                review_state=f.review_state,
            )
            for f in findings
        ],
    )
    return summary
