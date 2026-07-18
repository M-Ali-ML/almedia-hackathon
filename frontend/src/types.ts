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
  citations: Citation[]
  source_count?: number
  verified?: boolean
  verification_note?: string | null
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
