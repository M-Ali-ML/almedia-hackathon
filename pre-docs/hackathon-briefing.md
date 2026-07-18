# Cortea Track — Audit Fraud Agent Briefing

> **Challenge:** build an interactive agent an auditor can use to uncover layered fraud in a ~20-document dossier (German + English), where **every claim links to the exact document, page and passage**. Judged on an unseen final dossier. Flagging clean items counts against you. Prize: Meta x Ray-Ban AI Glasses per member.

## Files in this folder

| File | What it is |
|---|---|
| `README.md` | This briefing in markdown (readable on GitHub) |
| `hackathon-briefing.html` | Self-contained styled version — open in any browser |
| `hackathon-briefing.canvas.tsx` | Source of the Cursor canvas version |

At a glance: **36 files** in the sample dossier, **~32.5k** ledger/journal rows, **4 planted fraud schemes**, **7 decoys** (penalty if flagged).

> **The single most important strategic fact:** `data/info.md` is the answer key for the *sample* dossier only. Judging happens on a **different final dossier** with a regenerated scheme set. Anything hardcoded to Ratio Consulting, MV-U05, or specific amounts is worthless on judging day. Build **generalizable pattern detectors** (segregation-of-duties, capitalization policy, cut-off, threshold-splitting) that happen to catch these four — plus whatever else the final dossier contains.

---

## 1. What's actually in the dossier

The data is a GDPdU/GoBD export — the standardized German tax-audit data format (SAP-style semicolon-delimited text files, each folder described by an `index.xml` schema). This is exactly what a real German auditor receives from a client. Fictional company: Muster Verpackungen GmbH (packaging), fiscal year 2025.

| Folder / file | Contents | Rows | Watch out for |
|---|---|---|---|
| **Sachkonten/** | Chart of accounts + full general ledger postings | 43 + 20,258 | The core dataset. User IDs, posting dates, document numbers, Zahlung/Rechnung types |
| **Kreditoren/** | Vendor master data + vendor (AP) postings | 143 + 2,584 | VAT IDs, vendor creation — cross-reference against master-data change log |
| **Debitoren/** | Customer master data + customer (AR) postings | 160 + 3,749 | Mostly context; decoys D4/D7 live here |
| **AV/** | Fixed asset register + asset postings | 197 + 56 | Asset names betray misclassified repairs (F2-type schemes) |
| `Wareneingangsliste_2025.csv` | Goods-receipt list | 859 | The "did we actually get anything?" check for every vendor invoice |
| `Stammdatenaenderungen_2025.csv` | Master-data change log with GEAENDERT_VON / GENEHMIGT_VON | 20 | Creator = approver → broken four-eyes principle |
| `Berechtigungsauswertung_2025.xlsx` | User permission matrix (who can post, pay, create vendors) | xlsx | Segregation-of-duties analysis |
| `Fakturajournal_Januar_2026_Kreditoren.csv` + `Buchungen_Folgeperiode_2026.csv` | January 2026 invoices / next-period postings | 9 + 61 | Invoice date vs. service date (LEISTUNGSDATUM) → cut-off testing |
| Saldenliste 2024/2025, OP-Listen, Abstimmung xlsx | Trial balances, open-item lists, subledger reconciliation | xlsx | Tie financial statements back to the ledger |
| `Pruefungsplanung_JET_2025.docx` | Audit planning memo — states the €10,000 two-signature threshold | docx | Control thresholds come from prose documents, not data files |
| PDFs (JA-Entwurf, IT-Bestätigung, Exportprotokoll) | Draft financial statements, IT completeness confirmation | pdf | Reported profit figure to reconcile against |
| `Gesellschafterliste_Beteiligungen.csv` | Shareholder / related-party list | 6 | Disclosed related parties are decoys, undisclosed ones are findings |

**Data engineering gotchas (budget time for these):** Latin-1 / Windows-1252 encoding (umlauts are mangled if read as UTF-8) · German number format (1.234,56) · DD.MM.YYYY dates · semicolon-delimited CSVs · quoted text files with schemas defined only in `index.xml` · mixed formats: txt, csv, xlsx, docx, pdf. A clean ingestion layer that normalizes all of this into one queryable store is the unglamorous half of winning.

## 2. The fraud taxonomy (from the sample answer key)

Four schemes, layered by difficulty. Each is really a **reusable detection recipe** — the final dossier will use different names and numbers but the same class of manipulation (purchasing / assets / cut-off / controls).

### F1 — Fake vendor, cash misappropriation (€248,000) · *headline finding*

Shell vendor "Ratio Consulting GmbH" created mid-year, 5 round-amount "Beratung" invoices, all paid. Generalized recipe — a finding only earns top marks when **four independent sources converge**:

1. New vendor created mid-year with no prior-year balance
2. No goods receipt for any of its invoices
3. Creator = approver in the master-data change log
4. The same user holds posting + payment-run + vendor-creation rights in the permission matrix

Contrast with decoy D3 (Vega Werkstoffe): also new mid-year, but four-eyes approval and real deliveries → clean.

### F2 — Repairs capitalized as fixed assets (€150,800) · *profit overstated*

Six repair bills booked as asset additions instead of expense account 670000. Recipe: scan asset register for repair-vocabulary names (Reparatur, Instandsetzung, Austausch, Generalüberholung), match acquisition postings to vendor invoices via document numbers, flag where invoice text describes maintenance but the debit hits an asset account. Decoy D1 (€480k machine with a real investment request) is the trap — large and round is not the signal, wording vs. account is.

### F3 — December costs parked in January, no accrual (€192,000) · *profit overstated*

Eight invoices with FAKTURADATUM in Jan 2026 but LEISTUNGSDATUM in Dec 2025, goods received in December ("Rechnung offen"), and no year-end accrual booked. Recipe: join next-period invoice journal ↔ goods-receipt list ↔ ledger accruals; flag received-not-accrued items. Subtlety: a legitimate €86,500 accrual for other December work exists — the anomaly is the missing accrual on these specific items, not accruals in general.

### F4 — Payments split under the €10,000 approval limit (€39,040) · *control breach, no misstatement*

Four same-day payments to one vendor, each just under €10,000 (9,780 / 9,820 / 9,750 / 9,690). Recipe: read the approval threshold from the planning memo (a prose docx — the agent must extract policy from documents, not just crunch numbers), then group payments by vendor + date and flag clusters of near-threshold amounts.

**Impact:** F2 + F3 overstate profit by **€342,800** (reported €2.60m → true ~€2.26m). F1 is **€248,000** of cash stolen.

### The 7 decoys — where teams will lose points

| Decoy | Why it looks suspicious | Why it's clean |
|---|---|---|
| D1 · €480k machine | Large, round amount | Real investment request IA-2025-04 + real asset |
| D2 · Nord vs. Nordlicht Logistik | Near-duplicate vendor names | Different VAT-IDs, both have real goods receipts |
| D3 · Vega Werkstoffe | New vendor mid-year (like F1) | Four-eyes approval + real deliveries |
| D4 · Year-end volume bonuses | 22 customers credited at year-end | Documented rebate program, booked correctly |
| D5 · €220k Konzernumlage | Related-party payment to Austrian parent | Disclosed in shareholder list, arm's length |
| D6 · Asset scrapped for €1,200 | Book value ~€111,595 | Documented scrapping, not an under-value related-party sale |
| D7 · Invoice + credit note €18,500 | Same-period reversal | Revenue-neutral normal correction |

**What this means for the product:** the judging function is effectively precision-weighted — F1 found by combining sources = top marks, F2/F3 = core, F4 = bonus, any decoy accused = penalty. So the agent needs a **confidence / evidence-strength model** and an explicit "innocent explanation checked and ruled out" step per finding — not just an anomaly firehose.

## 3. Market research — Cortea (the track sponsor)

**€12M** seed round (June 2026) · founded **2024** in Berlin · **4,000+** audit reports processed last season · expanding across **UK, Germany, US**.

Cortea builds the **"AI quality layer" for audit firms** — Audit Quality Agents that review audit reports, financial statements, disclosure notes and workpapers before sign-off, cross-checking figures and supporting documentation for inconsistencies. Founded by Florian Neumann (ex-CTO of audibene, scaled 20 → 2,000 people) and Philipp Hövelmann (ex-KPMG auditor, early N26 / Banking Circle, engineering lead at Finoa). Team includes licensed CPAs and accredited IT auditors.

| Cortea principle | What it means for judging |
|---|---|
| **"White Box" AI** | "In a regulated world, results without a trail are useless" — a verifiable logic path from data to decision. Your evidence-linking UX is the product, not a feature. |
| **Auditor in control** | AI flags, drafts, analyses — the auditor reviews, approves, signs. Design for review workflow (accept / reject / annotate findings), not an autonomous verdict machine. |
| **Standards-grounded** | Everything aligned to ISA 315, ISA 240, IDW, HGB. Framing findings in audit language (management override, cut-off assertion, segregation of duties) will land with judges. |
| **German market DNA** | HGB / IDW / GDPdU-native. Handling the German data format and terminology fluently is table stakes for them. |

**Read-through:** this challenge is essentially Cortea's product thesis as a weekend exercise. The winning demo looks like a mini Cortea: fraud detection where every number is one click away from its source passage, with the human auditor making the final call. It is also a recruiting funnel — impressing them has value beyond the glasses.

## 4. Competitive landscape (what "state of the art" looks like)

| Player | Category | Approach worth stealing |
|---|---|---|
| **MindBridge** | Full-population risk scoring (closest analog) | Ensemble of ~28 rules + statistical + ML tests scores 100% of GL transactions; auditors drill into per-test "control point" results and build risk-stratified samples. Steal: named deterministic tests + a risk-score rollup per finding. |
| **DataSnipper** | Excel-native evidence matching | Every extraction is a "snip" visually anchored to the exact spot in the source PDF. Steal: click a number → the source document opens highlighted at the passage. This is the traceability bar. |
| **Cortea** | AI quality layer / disclosure & workpaper review | Finding → linked source material → review workflow with human sign-off. This is the judge's mental model. |
| **Fieldguide** | End-to-end AI audit platform | Engagement-level workflow; practitioners and agents collaborate. Less relevant for the weekend scope. |
| **Trullion** | Document-to-ledger traceability (ASC 606/842) | Bidirectional links between source docs and accounting treatment. |
| **CaseWare / TeamMate / IDEA** | Legacy incumbents | What the market is migrating away from — clunky UI is the incumbent weakness everyone attacks. |

Gap none of them fill in a hackathon-demo form: a conversational agent that autonomously runs cross-document forensic procedures, explains its reasoning in audit language, and cites document + row + passage for every claim. That gap is the product.

## 5. What to build — inputs for the PRD

### Layer 1 — Deterministic forensic engine

Ingestion normalizes all formats into one queryable store (encoding, dates, decimals, `index.xml` schemas). Then a library of named, generalizable tests: three-way match (invoice ↔ goods receipt ↔ payment), new-vendor risk profile, SoD / four-eyes violations, capitalization-vs-expense wording check, cut-off (service date vs. posting period vs. accruals), threshold-split clustering, Benford / round-amount stats, related-party vs. disclosure list. Deterministic = reliable on the unseen final dossier.

### Layer 2 — Agent + evidence-linked UI

An LLM agent that runs the test library, reads the prose documents (extracts policies like the €10k threshold), combines signals into findings, and drafts audit-language narratives. UI: findings ranked by evidence strength, each claim clickable through to the exact file, row or passage (highlighted); auditor accepts / rejects / annotates; chat for follow-up questions ("show me all payments to this vendor"). No number without a source — enforce it in the data model, not the prompt.

### Differentiators to prioritize (in order)

1. **Evidence chains** — every claim → doc + row/passage, one click. The literal judging criterion and Cortea's core thesis.
2. **Multi-source corroboration score per finding** — top marks require combining 4 sources for the F1-class finding.
3. **Explicit decoy handling** — "checked, innocent because…". Precision is scored; showing ruled-out items proves discipline.
4. **Policy extraction from prose docs (docx/pdf)** — separates you from teams who only crunch the CSVs.
5. **Financial-statement impact rollup** — reported vs. corrected profit. Turns findings into an audit conclusion, the "so what".
6. **Bilingual DE/EN handling** — table stakes but easy to fumble.

**De-risking the final dossier:** run the whole pipeline end-to-end on the sample dossier with the answer key hidden, measure precision/recall against `info.md`, and use the Slack auditor to validate borderline findings. The generator is seeded and adjustable — expect the same scheme families (purchasing, assets, cut-off, controls) with different entities and amounts.

---

*Sources: hackathon brief + sample answer key in `data/`, dossier extracted from `Uebungsdaten_Muster_Verpackungen.zip`, cortea.ai, EU-Startups (Jun 2026 seed announcement), MindBridge JET methodology papers, DataSnipper / Fieldguide / audit-automation market roundups (2026).*
