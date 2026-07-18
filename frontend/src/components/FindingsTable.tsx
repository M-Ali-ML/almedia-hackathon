import { Fragment, useState } from 'react'
import type { Citation, Finding } from '../types'

function LikelihoodChip({ value }: { value: number }) {
  const cls =
    value >= 70
      ? 'bg-red-100 text-red-700'
      : value >= 40
        ? 'bg-amber-100 text-amber-700'
        : 'bg-emerald-100 text-emerald-700'
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>
      {value}%
    </span>
  )
}

function CitationRow({ citation }: { citation: Citation }) {
  const locator = [
    citation.table && `table ${citation.table}`,
    citation.rows?.length ? `rows ${citation.rows.join(', ')}` : null,
    citation.sheet && `sheet ${citation.sheet}`,
    citation.page != null && `page ${citation.page}`,
    citation.passage,
  ]
    .filter(Boolean)
    .join(' · ')
  return (
    <li className="rounded-lg border border-slate-200 bg-slate-50 p-2.5">
      <div className="font-mono text-xs text-slate-700">
        <span className="font-semibold text-slate-900">{citation.file}</span>
        {locator && <span className="text-slate-500"> — {locator}</span>}
        <span className="ml-1 text-slate-400">[{citation.document_id}]</span>
      </div>
      {citation.excerpt && (
        <div className="mt-1.5 border-l-2 border-slate-300 pl-2 font-mono text-xs text-slate-600">
          {citation.excerpt}
        </div>
      )}
    </li>
  )
}

export function FindingsTable({
  findings,
  onChat,
}: {
  findings: Finding[]
  onChat: (f: Finding) => void
}) {
  const [expanded, setExpanded] = useState<string | null>(null)

  if (findings.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center text-slate-500 shadow-sm">
        The agent reported no findings for this dossier.
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-xs font-semibold tracking-wide text-slate-500 uppercase">
            <th className="px-4 py-3">ID</th>
            <th className="px-4 py-3">Finding</th>
            <th className="px-4 py-3">Impact</th>
            <th className="px-4 py-3">Likelihood</th>
            <th className="px-4 py-3">Evidence</th>
            <th className="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody>
          {findings.map((f) => (
            <Fragment key={f.id}>
              <tr
                className="cursor-pointer border-b border-slate-100 align-top hover:bg-slate-50"
                onClick={() => setExpanded(expanded === f.id ? null : f.id)}
              >
                <td className="px-4 py-3 font-mono text-xs font-semibold text-slate-900">{f.id}</td>
                <td className="max-w-xl px-4 py-3">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-semibold text-slate-900">{f.title}</span>
                    {f.status === 'needs_review' && (
                      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 uppercase">
                        Needs review
                      </span>
                    )}
                    {f.rule_ids.map((rule) => (
                      <span
                        key={rule}
                        className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-slate-600"
                      >
                        {rule}
                      </span>
                    ))}
                  </div>
                  <div className={`mt-1 text-slate-600 ${expanded === f.id ? '' : 'line-clamp-2'}`}>
                    {f.description}
                  </div>
                </td>
                <td className="px-4 py-3 font-mono text-xs whitespace-nowrap text-slate-700">
                  {f.amount_eur != null
                    ? f.amount_eur.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })
                    : '—'}
                </td>
                <td className="px-4 py-3">
                  <LikelihoodChip value={f.likelihood} />
                </td>
                <td className="px-4 py-3 text-xs text-slate-500">
                  {f.citations.length} source{f.citations.length === 1 ? '' : 's'}{' '}
                  <span className="text-slate-400">{expanded === f.id ? '▾' : '▸'}</span>
                </td>
                <td className="px-4 py-3">
                  <button
                    className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-700"
                    onClick={(e) => {
                      e.stopPropagation()
                      onChat(f)
                    }}
                  >
                    Chat with AI
                  </button>
                </td>
              </tr>
              {expanded === f.id && (
                <tr className="border-b border-slate-100 bg-slate-50/60">
                  <td />
                  <td colSpan={5} className="px-4 pt-1 pb-4">
                    <p className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">
                      Citations
                    </p>
                    <ul className="space-y-2">
                      {f.citations.map((c, i) => (
                        <CitationRow key={i} citation={c} />
                      ))}
                    </ul>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  )
}
