import type { ReactNode } from "react";
import {
  Callout,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Stack,
  Stat,
  Table,
  Text,
} from "cursor/canvas";

function SectionIntro({ children }: { children: ReactNode }) {
  return (
    <Text tone="secondary" style={{ maxWidth: 860 }}>
      {children}
    </Text>
  );
}

export default function HackathonBriefing() {
  return (
    <Stack gap={28} style={{ maxWidth: 1000, margin: "0 auto", padding: "8px 4px 48px" }}>
      <Stack gap={8}>
        <H1>Cortea Track — Audit Fraud Agent Briefing</H1>
        <Text tone="secondary">
          Challenge: build an interactive agent an auditor can use to uncover layered fraud in a
          ~20-document dossier (German + English), where <Text weight="semibold">every claim links to the exact
          document, page and passage</Text>. Judged on an unseen final dossier. Flagging clean items counts
          against you. Prize: Meta x Ray-Ban AI Glasses per member.
        </Text>
      </Stack>

      <Grid columns={4} gap={16}>
        <Stat value="36" label="Files in sample dossier" />
        <Stat value="~32.5k" label="Ledger / journal rows" />
        <Stat value="4" label="Planted fraud schemes" tone="danger" />
        <Stat value="7" label="Decoys (penalty if flagged)" tone="warning" />
      </Grid>

      <Callout tone="danger" title="The single most important strategic fact">
        `data/info.md` is the answer key for the sample dossier only. Judging happens on a{" "}
        <Text weight="semibold">different final dossier</Text> with a regenerated scheme set. Anything
        hardcoded to Ratio Consulting, MV-U05, or specific amounts is worthless on judging day. Build{" "}
        <Text weight="semibold">generalizable pattern detectors</Text> (segregation-of-duties, capitalization
        policy, cut-off, threshold-splitting) that happen to catch these four — plus whatever else the final
        dossier contains.
      </Callout>

      <Divider />

      <Stack gap={12}>
        <H2>1. What's actually in the dossier</H2>
        <SectionIntro>
          The data is a GDPdU/GoBD export — the standardized German tax-audit data format (SAP-style
          semicolon-delimited text files, each folder described by an `index.xml` schema). This is exactly
          what a real German auditor receives from a client. Fictional company: Muster Verpackungen GmbH
          (packaging), fiscal year 2025.
        </SectionIntro>
        <Table
          headers={["Folder / file", "Contents", "Rows", "Watch out for"]}
          rows={[
            [
              <Text weight="semibold">Sachkonten/</Text>,
              "Chart of accounts + full general ledger postings",
              "43 + 20,258",
              "The core dataset. User IDs, posting dates, document numbers, Zahlung/Rechnung types",
            ],
            [
              <Text weight="semibold">Kreditoren/</Text>,
              "Vendor master data + vendor (AP) postings",
              "143 + 2,584",
              "VAT IDs, vendor creation — cross-reference against master-data change log",
            ],
            [
              <Text weight="semibold">Debitoren/</Text>,
              "Customer master data + customer (AR) postings",
              "160 + 3,749",
              "Mostly context; decoys D4/D7 live here",
            ],
            [
              <Text weight="semibold">AV/</Text>,
              "Fixed asset register + asset postings",
              "197 + 56",
              "Asset names betray misclassified repairs (F2-type schemes)",
            ],
            [
              "Wareneingangsliste_2025.csv",
              "Goods-receipt list (859 rows)",
              "859",
              "The 'did we actually get anything?' check for every vendor invoice",
            ],
            [
              "Stammdatenaenderungen_2025.csv",
              "Master-data change log with GEAENDERT_VON / GENEHMIGT_VON",
              "20",
              "Creator = approver → broken four-eyes principle",
            ],
            [
              "Berechtigungsauswertung_2025.xlsx",
              "User permission matrix (who can post, pay, create vendors)",
              "xlsx",
              "Segregation-of-duties analysis",
            ],
            [
              "Fakturajournal_Januar_2026_Kreditoren.csv + Buchungen_Folgeperiode_2026.csv",
              "January 2026 invoices / next-period postings",
              "9 + 61",
              "Invoice date vs. service date (LEISTUNGSDATUM) → cut-off testing",
            ],
            [
              "Saldenliste 2024/2025, OP-Listen, Abstimmung xlsx",
              "Trial balances, open-item lists, subledger reconciliation",
              "xlsx",
              "Tie financial statements back to the ledger",
            ],
            [
              "Pruefungsplanung_JET_2025.docx",
              "Audit planning memo — states the €10,000 two-signature threshold",
              "docx",
              "Control thresholds come from prose documents, not data files",
            ],
            [
              "PDFs (JA-Entwurf, IT-Bestätigung, Exportprotokoll)",
              "Draft financial statements, IT completeness confirmation",
              "pdf",
              "Reported profit figure to reconcile against",
            ],
            [
              "Gesellschafterliste_Beteiligungen.csv",
              "Shareholder / related-party list",
              "6",
              "Disclosed related parties are decoys, undisclosed ones are findings",
            ],
          ]}
        />
        <Callout tone="warning" title="Data engineering gotchas (budget time for these)">
          Latin-1 / Windows-1252 encoding (umlauts are mangled if read as UTF-8) · German number format
          (1.234,56) · DD.MM.YYYY dates · semicolon-delimited CSVs · quoted text files with schemas defined
          only in `index.xml` · mixed formats: txt, csv, xlsx, docx, pdf. A clean ingestion layer that
          normalizes all of this into one queryable store is the unglamorous half of winning.
        </Callout>
      </Stack>

      <Divider />

      <Stack gap={12}>
        <H2>2. The fraud taxonomy (from the sample answer key)</H2>
        <SectionIntro>
          Four schemes, layered by difficulty. Each row is really a{" "}
          <Text weight="semibold">reusable detection recipe</Text> — the final dossier will use different
          names and numbers but the same class of manipulation (purchasing / assets / cut-off / controls).
        </SectionIntro>

        <Card>
          <CardHeader trailing={<Pill size="sm">headline finding</Pill>}>
            F1 — Fake vendor, cash misappropriation (€248,000)
          </CardHeader>
          <CardBody>
            <Stack gap={8}>
              <Text>
                Shell vendor "Ratio Consulting GmbH" created mid-year, 5 round-amount "Beratung" invoices,
                all paid. Generalized recipe — a finding only earns top marks when{" "}
                <Text weight="semibold">four independent sources converge</Text>:
              </Text>
              <Text tone="secondary">
                (1) new vendor created mid-year with no prior-year balance · (2) no goods receipt for any of
                its invoices · (3) creator = approver in the master-data change log · (4) the same user holds
                posting + payment-run + vendor-creation rights in the permission matrix. Contrast with decoy
                D3 (Vega Werkstoffe): also new mid-year, but four-eyes approval and real deliveries → clean.
              </Text>
            </Stack>
          </CardBody>
        </Card>

        <Card>
          <CardHeader trailing={<Pill size="sm">profit overstated</Pill>}>
            F2 — Repairs capitalized as fixed assets (€150,800)
          </CardHeader>
          <CardBody>
            <Text tone="secondary">
              Six repair bills booked as asset additions instead of expense account 670000. Recipe: scan asset
              register for repair-vocabulary names (Reparatur, Instandsetzung, Austausch, Generalüberholung),
              match acquisition postings to vendor invoices via document numbers, flag where invoice text
              describes maintenance but the debit hits an asset account. Decoy D1 (€480k machine with a real
              investment request) is the trap — large and round is not the signal, wording vs. account is.
            </Text>
          </CardBody>
        </Card>

        <Card>
          <CardHeader trailing={<Pill size="sm">profit overstated</Pill>}>
            F3 — December costs parked in January, no accrual (€192,000)
          </CardHeader>
          <CardBody>
            <Text tone="secondary">
              Eight invoices with FAKTURADATUM in Jan 2026 but LEISTUNGSDATUM in Dec 2025, goods received in
              December ("Rechnung offen"), and no year-end accrual booked. Recipe: join next-period invoice
              journal ↔ goods-receipt list ↔ ledger accruals; flag received-not-accrued items. Subtlety: a
              legitimate €86,500 accrual for other December work exists — the anomaly is the missing accrual
              on these specific items, not accruals in general.
            </Text>
          </CardBody>
        </Card>

        <Card>
          <CardHeader trailing={<Pill size="sm">control breach, no misstatement</Pill>}>
            F4 — Payments split under the €10,000 approval limit (€39,040)
          </CardHeader>
          <CardBody>
            <Text tone="secondary">
              Four same-day payments to one vendor, each just under €10,000 (9,780 / 9,820 / 9,750 / 9,690).
              Recipe: read the approval threshold from the planning memo (a prose docx — the agent must
              extract policy from documents, not just crunch numbers), then group payments by vendor + date
              and flag clusters of near-threshold amounts.
            </Text>
          </CardBody>
        </Card>

        <Grid columns={3} gap={16}>
          <Stat value="€342,800" label="Profit overstatement (F2 + F3)" tone="danger" />
          <Stat value="€2.60m → €2.26m" label="Reported vs. true profit" />
          <Stat value="€248,000" label="Cash stolen via fake vendor (F1)" tone="danger" />
        </Grid>

        <H3>The 7 decoys — where teams will lose points</H3>
        <Table
          headers={["Decoy", "Why it looks suspicious", "Why it's clean"]}
          rows={[
            ["D1 · €480k machine", "Large, round amount", "Real investment request IA-2025-04 + real asset"],
            ["D2 · Nord vs. Nordlicht Logistik", "Near-duplicate vendor names", "Different VAT-IDs, both have real goods receipts"],
            ["D3 · Vega Werkstoffe", "New vendor mid-year (like F1)", "Four-eyes approval + real deliveries"],
            ["D4 · Year-end volume bonuses", "22 customers credited at year-end", "Documented rebate program, booked correctly"],
            ["D5 · €220k Konzernumlage", "Related-party payment to Austrian parent", "Disclosed in shareholder list, arm's length"],
            ["D6 · Asset scrapped for €1,200", "Book value ~€111,595", "Documented scrapping, not an under-value related-party sale"],
            ["D7 · Invoice + credit note €18,500", "Same-period reversal", "Revenue-neutral normal correction"],
          ]}
          rowTone={["success", "success", "success", "success", "success", "success", "success"]}
        />
        <Callout tone="info" title="What this means for your product">
          The judging function is effectively precision-weighted: F1 found by combining sources = top marks,
          F2/F3 = core, F4 = bonus, any decoy accused = penalty. So the agent needs a{" "}
          <Text weight="semibold">confidence / evidence-strength model</Text> and an explicit
          "innocent explanation checked and ruled out" step per finding — not just an anomaly firehose.
        </Callout>
      </Stack>

      <Divider />

      <Stack gap={12}>
        <H2>3. Market research — Cortea (the track sponsor)</H2>
        <Grid columns={4} gap={16}>
          <Stat value="€12M" label="Seed round (June 2026)" />
          <Stat value="2024" label="Founded, Berlin" />
          <Stat value="4,000+" label="Audit reports processed last season" />
          <Stat value="UK · DE · US" label="Expansion markets" />
        </Grid>
        <Text>
          Cortea builds the <Text weight="semibold">"AI quality layer" for audit firms</Text> — Audit Quality
          Agents that review audit reports, financial statements, disclosure notes and workpapers before
          sign-off, cross-checking figures and supporting documentation for inconsistencies. Founded by
          Florian Neumann (ex-CTO of audibene, scaled 20 → 2,000 people) and Philipp Hövelmann (ex-KPMG
          auditor, early N26 / Banking Circle, engineering lead at Finoa). Team includes licensed CPAs and
          accredited IT auditors.
        </Text>
        <Table
          headers={["Cortea principle", "What it means for judging"]}
          rows={[
            [
              <Text weight="semibold">"White Box" AI</Text>,
              "\u201CIn a regulated world, results without a trail are useless\u201D — a verifiable logic path from data to decision. Your evidence-linking UX is the product, not a feature.",
            ],
            [
              <Text weight="semibold">Auditor in control</Text>,
              "AI flags, drafts, analyses — the auditor reviews, approves, signs. Design for review workflow (accept / reject / annotate findings), not an autonomous verdict machine.",
            ],
            [
              <Text weight="semibold">Standards-grounded</Text>,
              "Everything aligned to ISA 315, ISA 240, IDW, HGB. Framing findings in audit language (management override, cut-off assertion, segregation of duties) will land with judges.",
            ],
            [
              <Text weight="semibold">German market DNA</Text>,
              "HGB / IDW / GDPdU-native. Handling the German data format and terminology fluently is table stakes for them.",
            ],
          ]}
        />
        <Callout tone="success" title="Read-through">
          This challenge is essentially Cortea's product thesis as a weekend exercise. The winning demo looks
          like a mini Cortea: fraud detection where every number is one click away from its source passage,
          with the human auditor making the final call. It is also a recruiting funnel — impressing them has
          value beyond the glasses.
        </Callout>
      </Stack>

      <Stack gap={12}>
        <H2>4. Competitive landscape (what "state of the art" looks like)</H2>
        <SectionIntro>
          Useful both to steal proven interaction patterns and to know what judges consider baseline vs.
          impressive.
        </SectionIntro>
        <Table
          headers={["Player", "Category", "Approach worth stealing"]}
          rows={[
            [
              <Text weight="semibold">MindBridge</Text>,
              "Full-population risk scoring (closest analog)",
              "Ensemble of ~28 rules + statistical + ML tests scores 100% of GL transactions; auditors drill into per-test 'control point' results and build risk-stratified samples. Steal: named deterministic tests + a risk-score rollup per finding.",
            ],
            [
              <Text weight="semibold">DataSnipper</Text>,
              "Excel-native evidence matching",
              "Every extraction is a 'snip' visually anchored to the exact spot in the source PDF. Steal: click a number → the source document opens highlighted at the passage. This is the traceability bar.",
            ],
            [
              <Text weight="semibold">Cortea</Text>,
              "AI quality layer / disclosure & workpaper review",
              "Finding → linked source material → review workflow with human sign-off. This is the judge's mental model.",
            ],
            [
              <Text weight="semibold">Fieldguide</Text>,
              "End-to-end AI audit platform",
              "Engagement-level workflow; practitioners and agents collaborate. Less relevant for the weekend scope.",
            ],
            [
              <Text weight="semibold">Trullion</Text>,
              "Document-to-ledger traceability (ASC 606/842)",
              "Bidirectional links between source docs and accounting treatment.",
            ],
            [
              <Text weight="semibold">CaseWare / TeamMate / IDEA</Text>,
              "Legacy incumbents",
              "What the market is migrating away from — clunky UI is the incumbent weakness everyone attacks.",
            ],
          ]}
        />
        <Text tone="secondary">
          Gap none of them fill in a hackathon-demo form: a conversational agent that autonomously runs
          cross-document forensic procedures, explains its reasoning in audit language, and cites
          document + row + passage for every claim. That gap is your product.
        </Text>
      </Stack>

      <Divider />

      <Stack gap={12}>
        <H2>5. What to build — inputs for your PRD</H2>
        <Grid columns={2} gap={16}>
          <Card>
            <CardHeader>Layer 1 — Deterministic forensic engine</CardHeader>
            <CardBody>
              <Text tone="secondary">
                Ingestion normalizes all formats into one queryable store (encoding, dates, decimals,
                index.xml schemas). Then a library of named, generalizable tests: three-way match
                (invoice ↔ goods receipt ↔ payment), new-vendor risk profile, SoD / four-eyes violations,
                capitalization-vs-expense wording check, cut-off (service date vs. posting period vs.
                accruals), threshold-split clustering, Benford / round-amount stats, related-party vs.
                disclosure list. Deterministic = reliable on the unseen final dossier.
              </Text>
            </CardBody>
          </Card>
          <Card>
            <CardHeader>Layer 2 — Agent + evidence-linked UI</CardHeader>
            <CardBody>
              <Text tone="secondary">
                An LLM agent that runs the test library, reads the prose documents (extracts policies like
                the €10k threshold), combines signals into findings, and drafts audit-language narratives.
                UI: findings ranked by evidence strength, each claim clickable through to the exact file, row
                or passage (highlighted); auditor accepts / rejects / annotates; chat for follow-up questions
                ("show me all payments to this vendor"). No number without a source — enforce it in the data
                model, not the prompt.
              </Text>
            </CardBody>
          </Card>
        </Grid>
        <H3>Differentiators to prioritize (in order)</H3>
        <Table
          headers={["#", "Differentiator", "Why it wins"]}
          rows={[
            ["1", "Evidence chains: every claim → doc + row/passage, one click", "The literal judging criterion and Cortea's core thesis"],
            ["2", "Multi-source corroboration score per finding", "Top marks require combining 4 sources for the F1-class finding"],
            ["3", "Explicit decoy handling — 'checked, innocent because…'", "Precision is scored; showing ruled-out items proves discipline"],
            ["4", "Policy extraction from prose docs (docx/pdf)", "Separates you from teams who only crunch the CSVs"],
            ["5", "Financial-statement impact rollup (reported vs. corrected profit)", "Turns findings into an audit conclusion — the 'so what'"],
            ["6", "Bilingual DE/EN handling", "Table stakes but easy to fumble"],
          ]}
        />
        <Callout tone="neutral" title="De-risking the final dossier">
          Regenerate confidence before the deadline: run the whole pipeline end-to-end on the sample dossier
          with the answer key hidden, measure precision/recall against `info.md`, and use the Slack auditor to
          validate borderline findings. The generator is seeded and adjustable — expect the same scheme
          families (purchasing, assets, cut-off, controls) with different entities and amounts.
        </Callout>
      </Stack>

      <Text size="small" tone="tertiary">
        Sources: hackathon brief + sample answer key in `data/`, dossier extracted from
        Uebungsdaten_Muster_Verpackungen.zip, cortea.ai, EU-Startups (Jun 2026 seed announcement),
        MindBridge JET methodology papers, DataSnipper / Fieldguide / audit-automation market roundups (2026).
      </Text>
    </Stack>
  );
}
