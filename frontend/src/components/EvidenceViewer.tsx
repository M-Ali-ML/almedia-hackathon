import { useEffect, useState } from 'react'
import { getEvidence } from '../api'
import type { Citation, Evidence } from '../types'

function locatorLabel(c: Citation): string {
  return [
    c.table && `table ${c.table}`,
    c.rows?.length ? `rows ${c.rows.join(', ')}` : null,
    c.sheet && `sheet ${c.sheet}`,
    c.page != null && `page ${c.page}`,
    c.passage,
  ]
    .filter(Boolean)
    .join(' · ')
}

function highlight(text: string, needle?: string | null) {
  if (!needle) return text
  const idx = text.toLowerCase().indexOf(needle.toLowerCase())
  if (idx === -1) return text
  return (
    <>
      {text.slice(0, idx)}
      <mark className="rounded bg-amber-200 px-0.5">{text.slice(idx, idx + needle.length)}</mark>
      {text.slice(idx + needle.length)}
    </>
  )
}

function TableEvidence({ ev, citation }: { ev: Evidence; citation: Citation }) {
  // hide bookkeeping columns that add noise unless they carry the row id
  const columns = ev.columns.filter((c) => c === '_row_id' || !c.startsWith('_'))
  return (
    <div className="overflow-auto rounded-lg border border-slate-200">
      <table className="w-full text-left text-xs">
        <thead className="sticky top-0 bg-slate-100">
          <tr>
            {columns.map((c) => (
              <th key={c} className="px-3 py-2 font-semibold whitespace-nowrap text-slate-600">
                {c === '_row_id' ? 'row' : c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ev.rows.map((r) => (
            <tr
              key={r.row_id}
              className={
                r.cited
                  ? 'bg-amber-50 ring-1 ring-amber-300'
                  : 'border-t border-slate-100 text-slate-500'
              }
            >
              {columns.map((c) => (
                <td
                  key={c}
                  className={`px-3 py-1.5 font-mono whitespace-nowrap ${
                    r.cited ? 'text-slate-900' : ''
                  }`}
                >
                  {c === '_row_id' ? r.row_id : (r.values[c] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-slate-100 bg-slate-50 px-3 py-1.5 text-[11px] text-slate-400">
        Highlighted rows are the exact ones cited ({citation.rows?.join(', ')}); neighbouring rows
        shown for context.
      </p>
    </div>
  )
}

function ProseEvidence({ ev, citation }: { ev: Evidence; citation: Citation }) {
  return (
    <div className="space-y-3">
      {ev.passages.map((p, i) => (
        <div key={i} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
          <div className="mb-1 text-[11px] font-semibold tracking-wide text-slate-400 uppercase">
            {p.ref}
          </div>
          <p className="text-xs whitespace-pre-wrap text-slate-700">
            {highlight(p.text, citation.excerpt)}
          </p>
        </div>
      ))}
    </div>
  )
}

export function EvidenceViewer({
  batchId,
  citation,
  onClose,
}: {
  batchId: string
  citation: Citation
  onClose: () => void
}) {
  const [ev, setEv] = useState<Evidence | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setEv(null)
    setError(null)
    getEvidence(batchId, citation)
      .then((res) => !cancelled && setEv(res))
      .catch((e) => !cancelled && setError(String(e)))
    return () => {
      cancelled = true
    }
  }, [batchId, citation])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <p className="text-xs font-semibold tracking-wide text-slate-400 uppercase">Evidence</p>
            <p className="mt-0.5 font-mono text-sm font-semibold text-slate-900">
              {citation.file}
            </p>
            <p className="font-mono text-xs text-slate-500">{locatorLabel(citation)}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            ✕
          </button>
        </div>
        <div className="overflow-auto p-5">
          {error && <p className="text-sm text-red-600">{error}</p>}
          {!ev && !error && <p className="text-sm text-slate-500">Loading evidence…</p>}
          {ev?.kind === 'table' && <TableEvidence ev={ev} citation={citation} />}
          {ev?.kind === 'prose' && <ProseEvidence ev={ev} citation={citation} />}
          {ev?.kind === 'not_found' && (
            <p className="text-sm text-slate-500">{ev.detail ?? 'Evidence not found.'}</p>
          )}
        </div>
      </div>
    </div>
  )
}
