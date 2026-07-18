"""End-to-end smoke test on the sample dossier, no API key required.

Verifies the full mechanics with a scripted FunctionModel:
1. ingestion of the sample ZIP into the batch storage layout
2. deterministic K1-K7 candidate generation
3. the analysis run: candidates -> agent -> run_sql tool -> structured Finding
   with citations that reference real rows (validated against the DB)
4. the AG-UI chat endpoint over HTTP (SSE stream)

Run:  uv run python scripts/smoke_test.py [path/to/dossier.zip]
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

# The scripted FunctionModel replaces the real model, so no API key is needed;
# 'test' keeps agent construction from requiring OPENAI_API_KEY.
os.environ.setdefault("AUDITOR_MODEL", "test")

import duckdb
import httpx
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import storage  # noqa: E402
from app.agent import run_analysis  # noqa: E402
from app.agent.auditor import analysis_agent, chat_agent  # noqa: E402
from app.detection import run_detection  # noqa: E402
from app.ingestion import ingest_zip  # noqa: E402
from app.models import GlobalContext  # noqa: E402

BATCH_ID = "smoketest"
SAMPLE_ZIP = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else Path(__file__).resolve().parent.parent.parent / "data" / "Uebungsdaten_Muster_Verpackungen.zip"
)

RULE_HITS = []


def scripted_analysis(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Emit a finding whose citation is verified against the real ingested database."""
    report = {
        "investigations": [
            {
                "rule_hit_ids": [hit.id],
                "disposition": "finding" if hit.rule_id == "K1" else "dismissed",
                "reasoning": "Scripted smoke-test disposition.",
            }
            for hit in RULE_HITS
        ],
        "findings": [
            {
                "title": "Smoke-test finding",
                "description": "Vendor Delta Distribution SE exists (scripted check).",
                "likelihood": 10,
                "amount_eur": None,
                "status": "finding",
                "rule_ids": ["K1"],
                "rule_hit_ids": [next(hit.id for hit in RULE_HITS if hit.rule_id == "K1")],
                "citations": [
                    {
                        "document_id": "doc-024",
                        "file": "Uebungsdaten Muster Verpackungen/Kreditoren/Lieferanten.txt",
                        "table": "kreditoren__lieferanten",
                        "rows": [1],
                        "excerpt": "Delta Distribution SE",
                    }
                ],
            }
        ]
    }
    return ModelResponse(parts=[ToolCallPart("final_result", report)])


async def scripted_analysis_stream(messages: list[ModelMessage], info: AgentInfo):
    response = scripted_analysis(messages, info)
    for index, part in enumerate(response.parts):
        if isinstance(part, ToolCallPart):
            args = part.args if isinstance(part.args, str) else json.dumps(part.args)
            yield {
                index: DeltaToolCall(
                    name=part.tool_name,
                    json_args=args,
                    tool_call_id=part.tool_call_id,
                )
            }


async def scripted_chat_stream(messages: list[ModelMessage], info: AgentInfo):
    yield "Scripted chat reply "
    yield "about the finding."


async def main() -> None:
    # 1. ingestion into the real storage layout
    assert SAMPLE_ZIP.exists(), f"sample zip not found: {SAMPLE_ZIP}"
    work = storage.batch_dir(BATCH_ID)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    shutil.copy(SAMPLE_ZIP, work / "upload.zip")
    ingest = ingest_zip(work / "upload.zip", work)
    assert not ingest.warnings, f"ingestion warnings: {ingest.warnings}"
    assert len(ingest.documents) >= 20, "expected a full dossier"
    print(f"[1/4] ingestion OK — {len(ingest.documents)} documents, no warnings")

    # minimal global context file so instructions include the section
    (work / "global_context.json").write_text('{"items": []}')

    # 2. deterministic candidate generation
    global RULE_HITS
    detection = run_detection(storage.db_path(BATCH_ID), GlobalContext())
    RULE_HITS = detection.hits
    assert detection.summary.executed == ["K1", "K2", "K3", "K4", "K5", "K6", "K7"]
    hit_rules = {hit.rule_id for hit in RULE_HITS}
    assert {"K1", "K2", "K3", "K4", "K5"}.issubset(hit_rules), hit_rules
    print(f"[2/4] detection OK — {len(RULE_HITS)} candidates across {sorted(hit_rules)}")

    # 3. analysis with the scripted model
    with analysis_agent().override(model=FunctionModel(stream_function=scripted_analysis_stream)):
        findings = await run_analysis(BATCH_ID, RULE_HITS)
    assert len(findings) == 1, findings
    finding = findings[0]
    assert finding.id == "F-001" and finding.citations, finding
    citation = finding.citations[0]
    con = duckdb.connect(str(storage.db_path(BATCH_ID)), read_only=True)
    try:
        row = con.execute(
            f'SELECT lieferantenname FROM "{citation.table}" WHERE _row_id = ?', [citation.rows[0]]
        ).fetchone()
    finally:
        con.close()
    assert row and row[0] == citation.excerpt, (row, citation)
    print(f"[3/4] analysis OK — {finding.id} cites {citation.table} row {citation.rows[0]} = {row[0]!r}")

    # 4. AG-UI chat endpoint over HTTP (in-process ASGI)
    from app.main import app  # import late: loads .env, builds routes

    run_input = {
        "threadId": "t1",
        "runId": "r1",
        "state": {"batch_id": BATCH_ID, "finding": finding.model_dump()},
        "messages": [{"id": "m1", "role": "user", "content": "Summarize the evidence."}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }
    with chat_agent().override(model=FunctionModel(stream_function=scripted_chat_stream)):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/chat",
                json=run_input,
                headers={"accept": "text/event-stream"},
            )
    assert response.status_code == 200, (response.status_code, response.text[:500])
    events = [
        json.loads(line[5:].strip())
        for line in response.text.splitlines()
        if line.startswith("data:")
    ]
    types = [e["type"] for e in events]
    text = "".join(e.get("delta", "") for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")
    assert "RUN_STARTED" in types and "RUN_FINISHED" in types, types
    assert "Scripted chat reply" in text, text
    print(f"[4/4] AG-UI chat OK — events {types}, reply: {text!r}")

    print("\nSmoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
