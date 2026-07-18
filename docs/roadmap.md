# Next steps after the MVP

Not phases — a prioritized, concrete backlog. Ordered by judging leverage per `pre-docs/hackathon-briefing.md` (evidence chains > corroboration > decoy discipline > policy extraction > impact rollup) and the PRD/user stories. Each step builds on the MVP seams documented in `docs/mvp.md`.

## 1. Deterministic test library (biggest detection win)

Named, generalizable checks as plain SQL/Python functions over the batch DuckDB, exposed to the agent as tools and runnable standalone (PRD K1–K7, user stories 6–9):

- three-way match: vendor invoice ↔ goods receipt (`wareneingangsliste_2025`) ↔ payment
- new-vendor risk profile: created mid-year, no prior-year balance, first invoice fast
- segregation of duties / four-eyes: `stammdatenaenderungen` creator = approver, permission matrix cross-check
- capitalization wording check: repair vocabulary in asset names/postings vs. debited account
- cut-off: FAKTURADATUM vs. LEISTUNGSDATUM around year-end vs. accruals booked
- threshold-split clustering: same vendor + same day, amounts just under the approval limit from global context
- round-amount / off-hours / posting-user statistics

Rationale: deterministic tests are reliable on the unseen final dossier; the agent then combines and narrates the results instead of hunting from scratch. Cheaper, faster, more reproducible.

## 2. Verifier step + decoy discipline (protects the score)

Second agent (or second pass) that independently re-derives each finding's evidence via SQL before it reaches the UI, and records "checked, clean because …" for anomalies it rules out (user story 10). Add the ruled-out list to the UI — showing discipline is itself scored. Flagging clean items costs points, so this step pays for itself.

## 3. Multi-source corroboration score (top marks for the headline finding)

Replace the LLM's free likelihood guess with a computed score: how many *independent* documents support the finding (user story 11). The briefing is explicit that the F1-class finding only earns full marks when four sources converge. Keep the citation model as is — it already carries everything needed to count distinct `document_id`s.

## 4. Evaluation harness on the sample dossier (de-risks judging day)

Script that runs the full pipeline on `data/Uebungsdaten_Muster_Verpackungen.zip` with `data/info.md` kept out of all prompts, then compares findings against the answer key: recall on planted schemes, penalty count on decoys, wall-clock time (<10 min budget from the PRD). This is the feedback loop for every other improvement; without it we're tuning blind.

## 5. Auditor workflow: accept / reject / annotate (user story 4)

Persist a review state per finding (`accepted | rejected | annotated`, note text) in the batch result; buttons on each row. Small backend + UI change, big "auditor in control" signal for the Cortea judges.

## 6. Evidence viewer with highlighting (user story 3, the DataSnipper bar)

Click a citation → open the source file rendered server-side (table slice around `_row_id`, or DOCX/PDF text with the passage highlighted) instead of just showing the excerpt. Add `GET /api/batches/{id}/evidence?document_id&ref` returning the surrounding context.

## 7. Financial impact rollup (user story 12)

Reported profit (from the draft financial statements PDF, already in `document_texts`) vs. corrected profit after confirmed findings, shown as a header card. Turns findings into an audit conclusion — the "so what" differentiator.

## 8. Hardening, as needed rather than upfront

- XLSX ingestion: detect decorative header rows / real header line (Berechtigungsauswertung matrix is currently loosely typed)
- chat history persistence per finding; global (non-finding) chat
- parallel per-file summarizer agents if single-agent context becomes the bottleneck (architecture.md's multi-agent design) — only if the evaluation harness shows misses that summaries would fix
- runtime: cache global context per batch, stream analysis progress into the UI (AG-UI already supports it)

## Explicitly not planned

Authentication, multi-tenant concurrency, OCR, deployment — out of hackathon scope until the above is done.
