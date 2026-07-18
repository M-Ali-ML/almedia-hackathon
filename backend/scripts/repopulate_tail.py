"""Re-run the analysis + verifier tail on an already-ingested batch and save.

Used to refresh an existing batch's findings with newly added fields
(e.g. impact_type) without re-ingesting. Usage: python scripts/repopulate_tail.py <batch_id>
"""

import sys
from pathlib import Path

import anyio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import storage  # noqa: E402
from app.agent import run_analysis, run_verification  # noqa: E402


async def main(batch_id: str) -> None:
    result = storage.load_result(batch_id)
    if result is None:
        raise SystemExit(f"no result.json for {batch_id}")
    findings, ruled_out = await run_analysis(batch_id)
    findings, ruled_out = await run_verification(batch_id, findings, ruled_out)
    result.findings = findings
    result.ruled_out = ruled_out
    storage.save_result(result)
    print(f"saved {len(findings)} findings, {len(ruled_out)} ruled out")
    for f in findings:
        print(f"  {f.id} impact={f.impact_type:<22} verified={f.verified} "
              f"src={f.source_count} amt={f.amount_eur} — {f.title[:60]}")


if __name__ == "__main__":
    anyio.run(main, sys.argv[1] if len(sys.argv) > 1 else "4ca399ba06ac")
