# architecture.md: AI Auditor Fraud Detection MVP

## 1. High-Level Architecture & Tech Stack
To meet the strict 3-4 hour hackathon time limit while building a system capable of parsing complex, bilingual accounting data, the application will use a decoupled frontend and backend connected via standard API contracts.

*   **Frontend:** React and Tailwind CSS for a fast, responsive Single-Page Application (SPA).
*   **Backend:** Python utilizing Pydantic AI and the AGUI protocol to establish a seamless translation layer between the AI agents and the frontend.
*   **AI Models:** OpenAI will be the primary LLM provider, utilizing code interpreters (like Codex) to handle raw data extraction and manipulation where standard GPT models might struggle.
*   **Development Strategy:** Developers will establish API contracts and schemas within the first 20 minutes to prevent integration bottlenecks. An "Agent Log" text file will be maintained to synchronize the autonomous coding agents and ensure the parallel frontend and backend development streams do not overwrite each other.

## 2. Layer 1: Data Ingestion & Pre-Processing Pipeline
Real-world ERP data is notoriously messy. The unglamorous but critical first step is a deterministic data engineering layer that normalizes all inputs into one queryable database.

*   **Format Normalization:** The pipeline must ingest a mix of CSV, TXT, XLSX, PDF, and DOCX files.
*   **German Localization Parsing:** The system must specifically handle German quirks, including Latin-1/Windows-1252 text encoding, German decimal formats (`1.234,56`), and `DD.MM.YYYY` date structures.
*   **Data Cleaning:** The ingestion layer will rely on code interpreters to clean up chunked tables and deduplicate transactions caused by ERP system glitches.

## 3. Layer 2: Multi-Agent AI System
Because the accounting files are massive and LLMs have fixed context windows, the architecture utilizes a multi-agent system running parallel and sequential tasks.

*   **Agent 1: Parallel Summarizers (Pre-Analysis):** Multiple agents will run concurrently on individual files to extract crucial names, financial amounts, and policy limits (e.g., reading the €10,000 signature threshold from a Word document).
*   **Agent 2: Linkage Discovery:** Because the hardest fraud to catch requires combining isolated rows across different documents (e.g., an order in one file and a receipt in another), a specific process utilizing vector similarity will map out cross-file linkages.
*   **Agent 3: The Orchestrator:** This agent receives the combined summaries and linkage data. It is hardcoded with Journal Entry Testing (JET) procedures and specifically hunts for the target fraud patterns (F1-F4 / K1-K7), such as threshold splitting, cut-off errors, and fake vendors.
*   **Agent 4: The Verifier (Anti-Hallucination):** Because the hackathon penalizes teams for flagging clean "decoy" transactions, a secondary verifier agent independently reviews the orchestrator's claims. It acts as a safety net, explicitly ruling out innocent explanations (like four-eyes approvals or documented asset scrapping) before pushing the finding to the frontend.

## 4. Frontend & User Interface Workflow
The UI is designed around the "White Box" AI philosophy, ensuring the human auditor is always in control and can verify every claim. 

*   **Progress Tracking:** A single page where the user uploads a zip file and watches the pipeline progress through stages like "Pre-analyzing", "Ingesting", and "Analyzing".
*   **Results Dashboard:** A ranked list of suspected fraud rows. Each row displays a free-text description of the scheme and its financial impact.
*   **Ironclad Traceability:** **Every single finding must include a direct link to the exact document, row, page, and highlighted passage.** There can be no numbers presented without an underlying source.
*   **Human-in-the-Loop:** The auditor can explicitly accept, reject, or annotate each finding.
*   **Conversational Drill-Down:** Clicking a finding opens an accordion containing a chat interface, allowing the auditor to query the agent for deeper forensic reasoning (e.g., "show me all payments to this vendor").

## 5. Scoring & Confidence Logic
To optimize for the hackathon judging criteria, the backend will implement specific scoring logic:
*   **Multi-Source Corroboration:** The system assigns a higher confidence score to findings backed by multiple independent sources. For example, proving a fake vendor requires combining four distinct pieces of evidence (master-data logs, permission matrices, general ledgers, and goods receipts).
*   **Financial Impact Rollup:** The dashboard will calculate the total monetary impact of the confirmed frauds, displaying the company's originally reported profit versus the newly corrected true profit.