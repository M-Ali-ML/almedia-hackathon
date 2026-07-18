Here is the Product Requirements Document (PRD) structured specifically for your hackathon MVP, prioritizing the exact constraints, architectures, and fraud-detection strategies discussed by your team and the Cortea founder.

```markdown
# prd.md: AI Auditor Fraud Detection MVP

## 1. Product Overview
**Goal:** Build a specialized AI auditing application to identify hidden fraud cases within a provided dataset. 
**Constraint:** The development team has a strict 4 hour coding window, and the data processing pipeline must execute within 10 min to allow for testing iterations.
**Core Philosophy:** In auditing, missing a fraud is a far bigger problem than flagging a false positive. The system should lean toward over-detecting potential issues.

## 2. User Experience & UI (Frontend)
**Tech Stack:** React and Tailwind CSS.
**Design:** A highly simplified, single-page application.
*   **File Upload:** A primary interface to upload the provided zip file containing the standardized accounting data.
*   **Progress Indicators:** Visual states showing the pipeline progress (e.g., "Pre-analyzing", "Ingesting", "Analyzing").
*   **Results Dashboard:** A table/list of rows displaying potential fraud cases.
    *   **Row Identification:** Every result row must have a unique, visible ID so it can be referenced reliably in the UI and chat.
    *   **Row Details:** Each row will show its ID, a free-text description of the suspected fraud, and a likelihood score.
    *   **Crucial Hackathon Feature - Citations:** Each fraud claim must explicitly cite where the evidence was found (specific files and rows) so auditors can verify it.
    *   **Row Chat:** Each row has a simple "Chat with AI" action that opens a chat panel scoped to that row. The selected row ID and context are passed automatically so the user can ask follow-up questions about that finding.

## 3. System Architecture (Backend & AI)
**Tech Stack:** Python utilizing the AGUI protocol for seamless frontend/backend agent communication. 
**AI Model:** OpenAI (fallback plan relies heavily on prompt engineering/Codex with code interpreters to handle data messiness like chunked tables or duplicated rows).

**Multi-Agent Pipeline:**
1.  **Pre-Analysis/Ingestion:** Initial data extraction to pull out standard information (names, details, amounts, limits) and normalize the data before passing it to LLMs. 
2.  **Parallel Summarizer Agents:** Because ERP files are massive and LLMs have fixed context windows, parallel agents will summarize individual files or segments. 
3.  **Linkage Iteration:** A specific run to find cross-file linkages (e.g., joining an isolated receipt in one file to an order in another).
4.  **Orchestrator Agent:** This agent combines the summaries and linkage data to contextualize transactions and spot anomalies that only appear when looking at the whole picture.
5.  **Verifier Agent:** A secondary agent that reviews the orchestrator's fraud claims, asking for proof and verifying evidence to prevent the model from hallucinating false citations.

*Note: If the multi-agent system proves too complex for the time limit, the team will fallback to a single powerful agent equipped with hardcoded rules.*

## 4. Fraud Detection Logic (The "Brain")
The agents will not rely solely on "vibes" but will be hardcoded with structured auditing logic.
*   **JET Procedures:** The agents will be primed with Journal Entry Testing (JET) procedures, specifically the "Seven Whys" (who, what, where, why, etc.) to investigate the context of transactions.
*   **Targeted Rule Checks (K1-K7):** The prompts will explicitly hunt for specific known edge cases:
    *   **K1 & K2:** Fast payments to newly created vendors, or payments missing goods receipts/contracts.
    *   **K3:** Repairs incorrectly categorized as fixed assets to manipulate profits.
    *   **K4 (Cut-off Errors):** End-of-year profit manipulations where December bookings are shifted to January without accruals, or fake vendor profits are reversed in the new year.
    *   **K5 (Threshold Evasion):** Identifying multiple split payments just below approval limits (e.g., under €10,000) to avoid secondary managerial sign-off.
    *   **K6:** Statistically unusual large round amounts.
    *   **K7:** Suspicious off-hours bookings or entries made by managers instead of standard finance team members.

## 5. Execution Strategy & Collaboration
*   **API Contracts First:** To prevent bottlenecks, the team must define data schemas and API contracts between the frontend, backend, and agents within the first 20 minutes.
*   **Agent Log:** To ensure parallel coding does not overwrite contracts, developers will maintain an "Agent Log"—a shared file logging the latest technical changes so autonomous coding agents stay synced with their human counterparts.
```
