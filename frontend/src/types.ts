// Mirrors backend/app/models.py — keep in sync.

export interface Citation {
  document_id: string
  file: string
  table?: string | null
  rows?: number[] | null
  sheet?: string | null
  page?: number | null
  passage?: string | null
  excerpt?: string | null
}

export type ImpactType =
  | 'profit_overstatement'
  | 'cash_misappropriation'
  | 'control_breach'
  | 'disclosure'
  | 'other'

export type ReviewState = 'pending' | 'accepted' | 'rejected'

export interface Finding {
  id: string
  title: string
  description: string
  likelihood: number
  amount_eur?: number | null
  impact_type?: ImpactType
  citations: Citation[]
  source_count?: number
  verified?: boolean
  verification_note?: string | null
  review_state?: ReviewState
  review_note?: string | null
}

export interface EvidenceRow {
  row_id: number
  cited: boolean
  values: Record<string, string | null>
}

export interface Evidence {
  kind: 'table' | 'prose' | 'not_found'
  document_id?: string | null
  file?: string | null
  table?: string | null
  columns: string[]
  rows: EvidenceRow[]
  passages: { ref: string; text: string }[]
  detail?: string | null
}

export interface ImpactLine {
  id: string
  title: string
  impact_type: ImpactType
  amount_eur?: number | null
  review_state: ReviewState
}

export interface ImpactSummary {
  reported_profit_eur?: number | null
  reported_profit_source?: Citation | null
  profit_overstatement_eur: number
  corrected_profit_eur?: number | null
  cash_misappropriation_eur: number
  control_breach_count: number
  accepted_count: number
  pending_count: number
  total_flagged_eur: number
  lines: ImpactLine[]
}

export interface RuledOut {
  title: string
  reason: string
  check_id?: string | null
  citations: Citation[]
}

export interface ContextItem {
  kind: 'company_fact' | 'policy' | 'terminology' | 'document_relationship'
  statement: string
  citations: Citation[]
}

export interface GlobalContext {
  items: ContextItem[]
}

export interface DocumentInfo {
  document_id: string
  file: string
  kind: string
  table?: string | null
  row_count?: number | null
}

export type Stage =
  | 'queued'
  | 'extracting'
  | 'ingesting'
  | 'building_context'
  | 'analyzing'
  | 'done'
  | 'error'

export interface BatchStatus {
  batch_id: string
  stage: Stage
  detail?: string | null
  error?: string | null
}

export interface BatchResult {
  batch_id: string
  status: BatchStatus
  documents: DocumentInfo[]
  global_context?: GlobalContext | null
  findings: Finding[]
  ruled_out?: RuledOut[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}
