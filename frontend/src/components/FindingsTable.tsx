import { Fragment, useState } from 'react'
import type { Citation, Finding, RuleHit } from '../types'

function LikelihoodChip({ finding, ruleHits }: { finding: Finding; ruleHits: RuleHit[] }) {
  const value = finding.likelihood
  const cls =
    value >= 70
      ? 'bg-red-100 text-red-700'
      : value >= 40
        ? 'bg-amber-100 text-amber-700'
        : 'bg-emerald-100 text-emerald-700'
  const relatedHits = ruleHits.filter((hit) => finding.rule_hit_ids.includes(hit.id))
  const signals = [...new Set(relatedHits.flatMap((hit) => hit.signals))].slice(0, 6)
  const factors = finding.score_factors ?? []
  return (
    <span className="group relative inline-flex" tabIndex={0}>
      <span
        className={`inline-block cursor-help rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}
        aria-label={`Evidence strength ${value} percent`}
      >
        {value}%
      </span>
      <span className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-2 hidden w-80 -translate-x-1/2 rounded-xl bg-slate-950 p-3 text-left text-xs font-normal text-white shadow-xl group-hover:block group-focus:block">
        <span className="block font-semibold">Evidence strength: {value}/100</span>
        {factors.length > 0 ? (
          <span className="mt-2 block space-y-1">
            {factors.map((factor, index) => (
              <span key={`${factor.label}-${index}`} className="flex justify-between gap-3">
                <span className="text-slate-300">{factor.label}</span>
                <span className={factor.points < 0 ? 'text-amber-300' : 'text-emerald-300'}>
                  {factor.points > 0 ? '+' : ''}
                  {factor.points}
                </span>
              </span>
            ))}
          </span>
        ) : (
          <span className="mt-2 block text-slate-300">
            Legacy model-assessed score. Re-run this batch to see deterministic factors.
          </span>
        )}
        {signals.length > 0 && (
          <span className="mt-2 block border-t border-slate-700 pt-2">
            <span className="font-semibold text-slate-200">Signals</span>
            {signals.map((signal) => (
              <span key={signal} className="mt-1 block text-slate-300">
                • {signal}
              </span>
            ))}
          </span>
        )}
        <span className="mt-2 block border-t border-slate-700 pt-2 text-[10px] text-slate-400">
          This is evidence strength, not a statistical probability of fraud.
        </span>
      </span>
    </span>
  )
}

function CitationRow({ citation, batchId }: { citation: Citation; batchId: string }) {
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
        <a
          href={`/api/batches/${encodeURIComponent(batchId)}/documents/${encodeURIComponent(citation.document_id)}/file`}
          target="_blank"
          rel="noreferrer"
          className="font-semibold text-blue-700 underline decoration-blue-300 underline-offset-2 hover:text-blue-900"
        >
          {citation.file.split('/').at(-1) ?? citation.file}
        </a>
        {locator && <span className="text-slate-500"> — {locator}</span>}
        <span className="ml-1 text-slate-400">[{citation.document_id}]</span>
      </div>
      {citation.excerpt && (
        <div className="mt-1.5 line-clamp-3 border-l-2 border-slate-300 pl-2 font-mono text-xs text-slate-600">
          {citation.excerpt}
        </div>
      )}
    </li>
  )
}

export function FindingsTable({
  batchId,
  findings,
  ruleHits,
  onChat,
}: {
  batchId: string
  findings: Finding[]
  ruleHits: RuleHit[]
  onChat: (f: Finding) => void
}) {
  const [expanded, setExpanded] = useState<string | null>(null)

  if (findings.length === 0) {
    return (
      <div className="rounded-3xl border border-slate-200 bg-white p-10 text-center text-slate-500 shadow-sm">
        The agent reported no findings for this dossier.
      </div>
    )
  }

  return (
    <div className="overflow-visible rounded-3xl border border-slate-200 bg-white shadow-[0_16px_50px_-32px_rgba(15,23,42,0.35)]">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50/80">
          <tr className="border-b border-slate-200 text-xs font-semibold tracking-wide text-slate-500 uppercase">
            <th className="px-4 py-3">ID</th>
            <th className="px-4 py-3">Finding</th>
            <th className="px-4 py-3">Impact</th>
            <th className="px-4 py-3">Evidence strength</th>
            <th className="px-4 py-3">Evidence</th>
            <th className="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody>
          {findings.map((f) => (
            <Fragment key={f.id}>
              <tr
                className="cursor-pointer border-b border-slate-100 align-top transition-colors hover:bg-cyan-50/30"
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
                    {(f.rule_ids ?? []).map((rule) => (
                      <span
                        key={rule}
                        className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-slate-600"
                      >
                        {rule}
                      </span>
                    ))}
                  </div>
                  <div
                    className={`mt-1 leading-6 text-slate-600 ${expanded === f.id ? '' : 'line-clamp-3'}`}
                  >
                    {f.description}
                  </div>
                  <button
                    type="button"
                    className="mt-1.5 text-xs font-semibold text-cyan-700 hover:text-cyan-900 hover:underline"
                    aria-expanded={expanded === f.id}
                    onClick={(event) => {
                      event.stopPropagation()
                      setExpanded(expanded === f.id ? null : f.id)
                    }}
                  >
                    {expanded === f.id ? 'Show less' : 'Show full description'}
                  </button>
                </td>
                <td className="px-4 py-3 font-mono text-xs whitespace-nowrap text-slate-700">
                  {f.amount_eur != null
                    ? f.amount_eur.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })
                    : '—'}
                </td>
                <td className="px-4 py-3">
                  <LikelihoodChip finding={f} ruleHits={ruleHits} />
                </td>
                <td className="px-4 py-3 text-xs text-slate-500">
                  {f.citations.length} source{f.citations.length === 1 ? '' : 's'}{' '}
                  <span className="text-slate-400">{expanded === f.id ? '▾' : '▸'}</span>
                </td>
                <td className="px-4 py-3">
                  <button
                    className="rounded-lg bg-[#0b1f36] px-3 py-2 text-xs font-semibold whitespace-nowrap text-white shadow-sm transition hover:bg-cyan-700"
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
                        <CitationRow key={i} citation={c} batchId={batchId} />
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
