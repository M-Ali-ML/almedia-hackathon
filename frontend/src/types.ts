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

export interface Finding {
  id: string
  title: string
  description: string
  likelihood: number
  amount_eur?: number | null
  status: 'finding' | 'needs_review'
  rule_ids: string[]
  rule_hit_ids: string[]
  score_factors: { label: string; points: number }[]
  citations: Citation[]
}

export interface RuleHit {
  id: string
  rule_id: 'K1' | 'K2' | 'K3' | 'K4' | 'K5' | 'K6' | 'K7'
  subject_type: string
  subject_id: string
  title: string
  summary: string
  risk_score: number
  amount_eur?: number | null
  signals: string[]
  evidence: Citation[]
  counter_evidence: Citation[]
  missing_evidence: string[]
}

export interface DetectionSummary {
  executed: string[]
  skipped: Record<string, string>
  hit_counts: Record<string, number>
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
  | 'detecting'
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
  detection?: DetectionSummary | null
  rule_hits: RuleHit[]
  findings: Finding[]
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}
