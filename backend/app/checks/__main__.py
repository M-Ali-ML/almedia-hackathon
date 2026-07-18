"""Run the deterministic check library standalone on an ingested batch.

Usage:
    uv run python -m app.checks --batch <batch_id> [--approval-limit 10000] [--json]
"""

from __future__ import annotations

import argparse
import logging

from . import run_checks_for_batch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, help="batch id under data/batches/")
    parser.add_argument("--approval-limit", type=float, default=None)
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    params = {}
    if args.approval_limit is not None:
        params["approval_limit_eur"] = args.approval_limit
    report = run_checks_for_batch(args.batch, params)

    if args.json:
        print(report.model_dump_json(indent=2))
        return
    print(f"\nCheck report for batch {report.batch_id} — {report.total_hits} hits\n")
    for result in report.results:
        marker = {"ok": " ", "no_data": "-", "error": "!"}[result.status]
        print(f"[{marker}] {result.check_id}: {len(result.hits)} hits ({result.status})")
        for note in result.notes:
            print(f"      note: {note}")
        for hit in result.hits[:8]:
            print(f"      * {hit.summary}")
        if len(result.hits) > 8:
            print(f"      … {len(result.hits) - 8} more")
        print()


if __name__ == "__main__":
    main()
