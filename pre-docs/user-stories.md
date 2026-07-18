Based on the hackathon briefing documents, the dataset details, and the sponsor's specific judging criteria, here are the targeted user stories you need to achieve to win this hackathon. They are broken down by Data Ingestion, User Experience, Fraud Detection, and Scoring Optimization.

### 1. Data Engineering & Ingestion
*   **User Story 1: Normalizing Messy German Data**
    As the system backend, I need to reliably ingest and normalize various file formats (CSV, TXT, XLSX, PDF, DOCX) while handling German-specific quirks (Latin-1/Windows-1252 encoding, German `1.234,56` number formats, and `DD.MM.YYYY` dates), so that the AI can evaluate a single, clean, queryable database.
*   **User Story 2: Bilingual Processing**
    As the AI Agent, I need to process and understand documents natively in both English and German, so that I can accurately read the bilingual dossier provided by the judges.

### 2. Frontend & Auditor Workflow (The Core Product)
*   **User Story 3: Ironclad Traceability (One-Click Citations)**
    As an Auditor, I want every single fraud claim to include a direct link to the **exact document, row, page, and passage** (ideally highlighted), so that I can instantly verify the evidence without hunting for it manually. 
*   **User Story 4: Human-in-the-Loop Review**
    As an Auditor, I want to see a dashboard of ranked findings where I can explicitly **accept, reject, or annotate** each claim, so that I remain in full control of the final audit conclusion.
*   **User Story 5: Conversational Follow-up**
    As an Auditor, I want to use a chat interface on any flagged finding to ask follow-up questions (e.g., "show me all payments to this vendor"), so that I can dig deeper into the agent's forensic reasoning.

### 3. Fraud Detection Logic (The "Four Schemes")
*   **User Story 6: Detecting Fake Vendors & Broken Controls (F1)**
    As the AI Agent, I want to cross-reference master-data change logs, permission matrices, and goods receipts to identify fake vendors (e.g., the same user creating, approving, and paying a new vendor with no delivered goods), so that I can catch cash misappropriation.
*   **User Story 7: Detecting Capitalized Repairs (F2)**
    As the AI Agent, I want to scan the fixed asset register for repair-related vocabulary (e.g., "Reparatur", "Austausch") and check if the costs were illegally booked as assets instead of expenses, so that I can catch profit overstatements.
*   **User Story 8: Detecting Cut-Off Errors (F3)**
    As the AI Agent, I want to compare January invoice dates against December service dates and check the ledger for missing year-end accruals, so that I can flag costs intentionally shifted to the next year.
*   **User Story 9: Detecting Threshold-Splitting via Prose Extraction (F4)**
    As the AI Agent, I want to extract the company's payment-approval limits (e.g., €10,000) from unstructured prose documents (Word/PDFs) and group payments by date and vendor, so that I can flag malicious clusters of payments just below the signature limit.

### 4. Scoring Optimization & Decoy Handling
*   **User Story 10: Innocent Explanation Checking (Decoy Handling)**
    As the AI Agent, I need an explicit verification step to rule out innocent explanations for anomalies (e.g., a new vendor is fine if there are four-eyes approvals and real goods receipts), so that I do not penalize the team's score by flagging clean "decoy" items.
*   **User Story 11: Multi-Source Corroboration Scoring**
    As an Auditor, I want the system to assign a confidence score to each finding based on how many independent sources confirm it (e.g., top marks require 4 sources to prove a fake vendor), so that I know which claims are strongest.
*   **User Story 12: Financial Impact Rollup**
    As an Auditor, I want the dashboard to calculate the total monetary impact of the combined frauds, showing me the reported profit versus the corrected true profit, so that I understand the actual materiality of the findings.