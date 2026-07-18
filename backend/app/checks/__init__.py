"""Deterministic check library over a batch DuckDB (see library.py)."""

from __future__ import annotations

import logging
from typing import Any

import duckdb

from .. import storage
from .library import CHECKS_BY_ID, DEFAULT_PARAMS, run_checks, run_one_check
from .models import CheckHit, CheckReport, CheckResult

logger = logging.getLogger(__name__)

__all__ = [
    "CheckHit",
    "CheckReport",
    "CheckResult",
    "CHECKS_BY_ID",
    "DEFAULT_PARAMS",
    "run_checks",
    "run_one_check",
    "run_checks_for_batch",
    "load_check_report",
]


def run_checks_for_batch(batch_id: str, params: dict[str, Any] | None = None) -> CheckReport:
    """Run all checks against a batch database and persist checks.json."""
    con = duckdb.connect(str(storage.db_path(batch_id)), read_only=True)
    try:
        results = run_checks(con, params)
    finally:
        con.close()
    report = CheckReport(
        batch_id=batch_id,
        parameters={**DEFAULT_PARAMS, **(params or {})},
        results=results,
    )
    path = storage.batch_dir(batch_id) / "checks.json"
    path.write_text(report.model_dump_json(indent=2))
    logger.info(
        "[%s] checks complete — %d hits across %d checks -> %s",
        batch_id,
        report.total_hits,
        len(report.results),
        path.name,
    )
    return report


def load_check_report(batch_id: str) -> CheckReport | None:
    path = storage.batch_dir(batch_id) / "checks.json"
    if not path.exists():
        return None
    return CheckReport.model_validate_json(path.read_text())
