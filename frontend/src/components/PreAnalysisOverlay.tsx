import { useEffect, useMemo } from 'react'
import type { BatchResult, Citation, ContextItem, DocumentInfo } from '../types'

function SourceLink({ batchId, citation }: { batchId: string; citation: Citation }) {
  const locator = citation.page
    ? `page ${citation.page}`
    : citation.passage
      ? /^(paragraph|table)\s+\d+/i.test(citation.passage)
        ? citation.passage
        : 'passage'
      : citation.rows?.length
        ? `rows ${citation.rows.join(', ')}`
        : null
  return (
    <a
      href={`/api/batches/${encodeURIComponent(batchId)}/documents/${encodeURIComponent(citation.document_id)}/file`}
      target="_blank"
      rel="noreferrer"
      className="inline-flex max-w-full items-center gap-1 rounded-md bg-slate-100 px-2 py-1 font-mono text-[11px] text-blue-700 hover:bg-blue-50 hover:text-blue-900"
    >
      <span className="truncate">{citation.file.split('/').at(-1) ?? citation.file}</span>
      {locator && <span className="shrink-0 text-slate-400">· {locator}</span>}
      <span aria-hidden="true">↗</span>
    </a>
  )
}

function ContextSection({
  title,
  description,
  items,
  batchId,
}: {
  title: string
  description: string
  items: ContextItem[]
  batchId: string
}) {
  if (items.length === 0) return null
  return (
    <section>
      <div className="mb-3">
        <h3 className="text-sm font-bold text-slate-900">{title}</h3>
        <p className="mt-0.5 text-xs text-slate-500">{description}</p>
      </div>
      <div className="space-y-2">
        {items.map((item, index) => (
          <article key={`${item.kind}-${index}`} className="rounded-xl border border-slate-200 p-3">
            <p className="text-sm leading-5 text-slate-700">{item.statement}</p>
            {item.citations.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {item.citations.map((citation, citationIndex) => (
                  <SourceLink
                    key={`${citation.document_id}-${citationIndex}`}
                    batchId={batchId}
                    citation={citation}
                  />
                ))}
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  )
}

function DataInventory({ batchId, documents }: { batchId: string; documents: DocumentInfo[] }) {
  const groups = useMemo(() => {
    const result = new Map<string, DocumentInfo[]>()
    for (const document of documents) {
      const group = result.get(document.kind) ?? []
      group.push(document)
      result.set(document.kind, group)
    }
    return [...result.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [documents])

  return (
    <section>
      <div className="mb-3">
        <h3 className="text-sm font-bold text-slate-900">Data inventory</h3>
        <p className="mt-0.5 text-xs text-slate-500">
          Files and tables available to the audit procedures, with their ingested populations.
        </p>
      </div>
      <div className="overflow-hidden rounded-xl border border-slate-200">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-3 py-2 font-semibold">Source</th>
              <th className="px-3 py-2 font-semibold">Type</th>
              <th className="px-3 py-2 text-right font-semibold">Rows / passages</th>
            </tr>
          </thead>
          <tbody>
            {groups.flatMap(([kind, docs]) =>
              docs.map((document) => (
                <tr key={`${document.document_id}-${document.table ?? ''}`} className="border-t border-slate-100">
                  <td className="max-w-sm px-3 py-2">
                    <a
                      href={`/api/batches/${encodeURIComponent(batchId)}/documents/${encodeURIComponent(document.document_id)}/file`}
                      target="_blank"
                      rel="noreferrer"
                      className="font-medium text-blue-700 hover:underline"
                    >
                      {document.file.split('/').at(-1) ?? document.file}
                    </a>
                    {document.table && (
                      <p className="mt-0.5 truncate font-mono text-[10px] text-slate-400">{document.table}</p>
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-500">{kind.replaceAll('_', ' ')}</td>
                  <td className="px-3 py-2 text-right font-mono text-slate-600">
                    {document.row_count?.toLocaleString() ?? '—'}
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export function PreAnalysisOverlay({ batch, onClose }: { batch: BatchResult; onClose: () => void }) {
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  const context = batch.global_context?.items ?? []
  const policies = context.filter((item) => item.kind === 'policy')
  const companyFacts = context.filter((item) => item.kind === 'company_fact')
  const terminology = context.filter((item) => item.kind === 'terminology')
  const relationships = context.filter((item) => item.kind === 'document_relationship')
  const executed = batch.detection?.executed ?? []
  const skipped = batch.detection?.skipped ?? {}
  const candidateCount = batch.rule_hits.length

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-sm" onMouseDown={onClose}>
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="pre-analysis-title"
        className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="flex items-start justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <p className="text-xs font-semibold tracking-wide text-blue-700 uppercase">Batch {batch.batch_id}</p>
            <h2 id="pre-analysis-title" className="mt-1 text-xl font-bold text-slate-950">
              Pre-analysis overview
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-slate-500">
              Source-grounded company context, ingested data coverage, and readiness for K1–K7 fraud analysis.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="Close pre-analysis"
          >
            ✕
          </button>
        </header>

        <div className="overflow-y-auto px-6 py-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ['Documents', batch.documents.length],
              ['Context items', context.length],
              ['Checks executed', executed.length],
              ['Candidates', candidateCount],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs font-medium text-slate-500">{label}</p>
                <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
              </div>
            ))}
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="space-y-7">
              <ContextSection
                title="Company policies and audit parameters"
                description="Company-specific thresholds and control expectations extracted from source documents."
                items={policies}
                batchId={batch.batch_id}
              />
              <ContextSection
                title="Company and accounting context"
                description="Source assertions and financial context used when interpreting anomalies."
                items={companyFacts}
                batchId={batch.batch_id}
              />
              <ContextSection
                title="Terminology and document relationships"
                description="Definitions and links that help the agent navigate the dossier."
                items={[...terminology, ...relationships]}
                batchId={batch.batch_id}
              />
            </div>

            <div className="space-y-7">
              <section>
                <div className="mb-3">
                  <h3 className="text-sm font-bold text-slate-900">Analysis readiness</h3>
                  <p className="mt-0.5 text-xs text-slate-500">
                    Which deterministic fraud procedures ran and how many candidates they produced.
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 p-3">
                  <div className="grid grid-cols-2 gap-2">
                    {(['K1', 'K2', 'K3', 'K4', 'K5', 'K6', 'K7'] as const).map((rule) => {
                      const wasExecuted = executed.includes(rule)
                      const reason = skipped[rule]
                      return (
                        <div key={rule} className="rounded-lg bg-slate-50 p-2.5">
                          <div className="flex items-center justify-between">
                            <span className="font-mono text-xs font-bold text-slate-800">{rule}</span>
                            <span className={`text-[10px] font-semibold uppercase ${wasExecuted ? 'text-emerald-700' : 'text-amber-700'}`}>
                              {wasExecuted ? 'Ready' : 'Skipped'}
                            </span>
                          </div>
                          <p className="mt-1 text-xs text-slate-500">
                            {wasExecuted
                              ? `${batch.detection?.hit_counts[rule] ?? 0} candidate(s)`
                              : reason ?? 'Not executed yet'}
                          </p>
                        </div>
                      )
                    })}
                  </div>
                  {!batch.detection && (
                    <p className="mt-3 text-xs text-amber-700">
                      Detection has not run for this batch. Re-run it with the current backend to see readiness details.
                    </p>
                  )}
                </div>
              </section>
              <DataInventory batchId={batch.batch_id} documents={batch.documents} />
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
