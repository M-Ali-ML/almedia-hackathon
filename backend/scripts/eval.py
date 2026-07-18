"""Evaluation harness: score the pipeline against the sample-dossier answer key.

Runs the pipeline on data/Uebungsdaten_Muster_Verpackungen.zip (the answer key
in eval/answer_key.yaml is used for scoring ONLY and never enters any prompt),
then reports per-scheme recall (F1-F4), decoy false positives (D1-D7), and
wall-clock timings against the 10-minute budget. Every run is archived under
eval/runs/ so pipeline variants can be compared.

Usage:
    uv run python scripts/eval.py                     # full pipeline run (needs OPENAI_API_KEY)
    uv run python scripts/eval.py --reuse-batch ID    # copy ingest+context from batch ID, re-run analysis only
    uv run python scripts/eval.py --score-only ID     # just score the existing result.json of batch ID
    uv run python scripts/eval.py --label baseline    # tag the archived run record

Exit code is non-zero when detection is below target (--min-schemes, default
all 4) or decoys are flagged (--max-decoys, default 0), so this doubles as CI.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")
load_dotenv(BACKEND.parent / ".env")

DEFAULT_ZIP = BACKEND.parent / "data" / "Uebungsdaten_Muster_Verpackungen.zip"
KEY_PATH = BACKEND / "eval" / "answer_key.yaml"
RUNS_DIR = BACKEND / "eval" / "runs"
TIME_BUDGET_S = 600  # PRD: pipeline must finish within 10 minutes


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _finding_text(finding: dict[str, Any]) -> str:
    """All searchable text of a finding, lowercased."""
    parts = [str(finding.get("title", "")), str(finding.get("description", ""))]
    for citation in finding.get("citations") or []:
        for key in ("file", "table", "sheet", "passage", "excerpt"):
            value = citation.get(key)
            if value:
                parts.append(str(value))
    return "\n".join(parts).lower()


def _matched_terms(text: str, terms: list[str]) -> list[str]:
    return [t for t in terms if t.lower() in text]


def score(findings: list[dict[str, Any]], key: dict[str, Any]) -> dict[str, Any]:
    texts = {f["id"]: _finding_text(f) for f in findings}
    titles = {f["id"]: f.get("title", "") for f in findings}

    schemes: list[dict[str, Any]] = []
    scheme_finding_ids: set[str] = set()
    for scheme in key["schemes"]:
        matched_by = []
        for fid, text in texts.items():
            terms = _matched_terms(text, scheme["match_any"])
            if terms:
                matched_by.append({"finding_id": fid, "terms": terms})
                scheme_finding_ids.add(fid)
        schemes.append(
            {
                "id": scheme["id"],
                "title": scheme["title"],
                "detected": bool(matched_by),
                "matched_by": matched_by,
            }
        )

    # A decoy only counts as flagged when a finding that matches NO real scheme
    # mentions it; scheme findings may legitimately cite decoys as ruled-out
    # contrast (e.g. Vega Werkstoffe next to the F1 fake vendor).
    decoys: list[dict[str, Any]] = []
    decoy_finding_ids: set[str] = set()
    for decoy in key["decoys"]:
        flagged_by, mentioned_by = [], []
        for fid, text in texts.items():
            terms = _matched_terms(text, decoy["match_any"])
            if not terms:
                continue
            entry = {"finding_id": fid, "terms": terms}
            if fid in scheme_finding_ids:
                mentioned_by.append(entry)
            else:
                flagged_by.append(entry)
                decoy_finding_ids.add(fid)
        decoys.append(
            {
                "id": decoy["id"],
                "title": decoy["title"],
                "flagged": bool(flagged_by),
                "flagged_by": flagged_by,
                "mentioned_by": mentioned_by,
            }
        )

    unmatched = [
        {"finding_id": fid, "title": titles[fid]}
        for fid in texts
        if fid not in scheme_finding_ids and fid not in decoy_finding_ids
    ]

    return {
        "counts": {
            "findings": len(findings),
            "schemes_detected": sum(1 for s in schemes if s["detected"]),
            "schemes_total": len(schemes),
            "decoys_flagged": sum(1 for d in decoys if d["flagged"]),
        },
        "schemes": schemes,
        "decoys": decoys,
        "unmatched_findings": unmatched,
    }


# ---------------------------------------------------------------------------
# Pipeline drivers
# ---------------------------------------------------------------------------


async def run_full(zip_path: Path, batch_id: str, timings: dict[str, float]) -> list[dict]:
    from app import storage
    from app.agent import build_global_context, run_analysis
    from app.ingestion import ingest_zip
    from app.models import BatchResult, BatchStatus

    work = storage.batch_dir(batch_id)
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy(zip_path, work / "upload.zip")

    t0 = time.monotonic()
    ingest = ingest_zip(work / "upload.zip", work)
    timings["ingest"] = time.monotonic() - t0
    if ingest.warnings:
        print(f"! ingestion warnings: {ingest.warnings}")

    from app.checks import run_checks_for_batch

    t0 = time.monotonic()
    run_checks_for_batch(batch_id)
    timings["checks"] = time.monotonic() - t0

    t0 = time.monotonic()
    context = await build_global_context(batch_id)
    timings["context"] = time.monotonic() - t0

    t0 = time.monotonic()
    findings, ruled_out = await run_analysis(batch_id)
    timings["analysis"] = time.monotonic() - t0

    result = BatchResult(
        batch_id=batch_id,
        status=BatchStatus(batch_id=batch_id, stage="done", detail=f"{len(findings)} findings (eval)"),
        documents=ingest.documents,
        global_context=context,
        findings=findings,
        ruled_out=ruled_out,
    )
    storage.save_result(result)
    return [f.model_dump() for f in findings]


async def run_reuse(source_batch: str, batch_id: str, timings: dict[str, float]) -> list[dict]:
    """Copy the ingested DB + global context from an existing batch, re-run analysis only."""
    from app import storage
    from app.agent import run_analysis
    from app.models import BatchResult, BatchStatus

    source = storage.batch_dir(source_batch)
    if not (source / "dossier.duckdb").exists():
        raise SystemExit(f"source batch '{source_batch}' has no dossier.duckdb")
    work = storage.batch_dir(batch_id)
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy(source / "dossier.duckdb", work / "dossier.duckdb")
    if (source / "global_context.json").exists():
        shutil.copy(source / "global_context.json", work / "global_context.json")

    from app.checks import run_checks_for_batch

    t0 = time.monotonic()
    run_checks_for_batch(batch_id)
    timings["checks"] = time.monotonic() - t0

    t0 = time.monotonic()
    findings, ruled_out = await run_analysis(batch_id)
    timings["analysis"] = time.monotonic() - t0

    source_result = storage.load_result(source_batch)
    result = BatchResult(
        batch_id=batch_id,
        status=BatchStatus(batch_id=batch_id, stage="done", detail=f"{len(findings)} findings (eval)"),
        documents=source_result.documents if source_result else [],
        global_context=source_result.global_context if source_result else None,
        findings=findings,
        ruled_out=ruled_out,
    )
    storage.save_result(result)
    return [f.model_dump() for f in findings]


def load_existing_findings(batch_id: str) -> list[dict]:
    from app import storage

    result = storage.load_result_dict(batch_id)
    if result is None:
        raise SystemExit(f"batch '{batch_id}' has no result.json")
    return result.get("findings", [])


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(report: dict[str, Any]) -> None:
    c = report["scores"]["counts"]
    print()
    print("=" * 64)
    print(f"EVAL  mode={report['mode']}  batch={report['batch_id']}  model={report['model']}")
    print("=" * 64)
    print(f"Findings produced: {c['findings']}")
    print(f"\nSchemes detected: {c['schemes_detected']}/{c['schemes_total']}")
    for s in report["scores"]["schemes"]:
        if s["detected"]:
            via = "; ".join(
                f"{m['finding_id']} ({', '.join(m['terms'][:3])})" for m in s["matched_by"]
            )
            print(f"  {s['id']}  HIT   {s['title']}\n        via {via}")
        else:
            print(f"  {s['id']}  MISS  {s['title']}")
    print(f"\nDecoys flagged (penalty): {c['decoys_flagged']}")
    for d in report["scores"]["decoys"]:
        if d["flagged"]:
            via = "; ".join(
                f"{m['finding_id']} ({', '.join(m['terms'][:3])})" for m in d["flagged_by"]
            )
            print(f"  {d['id']}  FLAGGED  {d['title']}\n        by {via}")
        elif d["mentioned_by"]:
            fids = ", ".join(m["finding_id"] for m in d["mentioned_by"])
            print(f"  {d['id']}  ok (mentioned inside scheme finding(s) {fids})")
    if report["scores"]["unmatched_findings"]:
        print("\nFindings not matched to key (inspect manually — possible FPs):")
        for f in report["scores"]["unmatched_findings"]:
            print(f"  {f['finding_id']}  {f['title']}")
    if report["timings_s"]:
        parts = ", ".join(f"{k} {v:.1f}s" for k, v in report["timings_s"].items())
        total = report["timings_s"].get("total", 0.0)
        budget = "OK" if total <= TIME_BUDGET_S else "OVER BUDGET"
        print(f"\nTimings: {parts}  (budget {TIME_BUDGET_S}s: {budget})")
    print(f"\nRESULT: {'PASS' if report['passed'] else 'FAIL'}  — {report['verdict']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP, help="dossier zip for full runs")
    parser.add_argument("--reuse-batch", metavar="ID", help="reuse ingest+context of batch ID, re-run analysis")
    parser.add_argument("--score-only", metavar="ID", help="score the existing result.json of batch ID")
    parser.add_argument("--label", default=None, help="tag for the archived run record")
    parser.add_argument("--model", default=None, help="override AUDITOR_MODEL for this run")
    parser.add_argument("--min-schemes", type=int, default=4)
    parser.add_argument("--max-decoys", type=int, default=0)
    args = parser.parse_args()

    if args.model:
        import os

        os.environ["AUDITOR_MODEL"] = args.model

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    key = yaml.safe_load(KEY_PATH.read_text())
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
    timings: dict[str, float] = {}
    t_start = time.monotonic()

    if args.score_only:
        mode, batch_id = "score-only", args.score_only
        findings = load_existing_findings(batch_id)
    elif args.reuse_batch:
        mode, batch_id = "reuse", f"eval-{stamp}"
        findings = asyncio.run(run_reuse(args.reuse_batch, batch_id, timings))
    else:
        mode, batch_id = "full", f"eval-{stamp}"
        if not args.zip.exists():
            raise SystemExit(f"dossier zip not found: {args.zip}")
        findings = asyncio.run(run_full(args.zip, batch_id, timings))

    if timings:
        timings["total"] = time.monotonic() - t_start

    scores = score(findings, key)
    c = scores["counts"]
    passed = c["schemes_detected"] >= args.min_schemes and c["decoys_flagged"] <= args.max_decoys
    verdict = (
        f"schemes {c['schemes_detected']}/{c['schemes_total']} (min {args.min_schemes}), "
        f"decoys flagged {c['decoys_flagged']} (max {args.max_decoys})"
    )

    import os

    report = {
        "timestamp": stamp,
        "label": args.label,
        "mode": mode,
        "batch_id": batch_id,
        "model": os.environ.get("AUDITOR_MODEL", "openai:gpt-5.1"),
        "scores": scores,
        "timings_s": {k: round(v, 1) for k, v in timings.items()},
        "passed": passed,
        "verdict": verdict,
    }

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_path = RUNS_DIR / f"{stamp}{'-' + args.label if args.label else ''}-{mode}.json"
    run_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print_report(report)
    print(f"Run record: {run_path.relative_to(BACKEND)}")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
