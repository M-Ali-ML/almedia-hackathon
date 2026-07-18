import { useState } from 'react'
import type { Citation, Finding, ImpactType, ReviewState } from '../types'

const IMPACT_LABELS: Record<ImpactType, string> = {
  profit_overstatement: 'Profit overstatement',
  cash_misappropriation: 'Cash misappropriation',
  control_breach: 'Control breach',
  disclosure: 'Disclosure',
  other: 'Other',
}

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

function VerifiedBadge({ f }: { f: Finding }) {
  if (f.verified) {
    return (
      <span
        title={f.verification_note ?? 'Independently confirmed by the verifier pass'}
        className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-700"
      >
        ✓ Verified{f.source_count ? ` · ${f.source_count} sources` : ''}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">
      Unverified
    </span>
  )
}

function ReviewBadge({ state }: { state: ReviewState }) {
  if (state === 'accepted')
    return (
      <span className="rounded-full bg-emerald-600 px-2 py-0.5 text-[11px] font-semibold text-white">
        Accepted
      </span>
    )
  if (state === 'rejected')
    return (
      <span className="rounded-full bg-slate-400 px-2 py-0.5 text-[11px] font-semibold text-white">
        Rejected
      </span>
    )
  return null
}

function CitationRow({
  citation,
  onOpen,
}: {
  citation: Citation
  onOpen: (c: Citation) => void
}) {
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
    <li>
      <button
        onClick={() => onOpen(citation)}
        className="w-full rounded-lg border border-slate-200 bg-slate-50 p-2.5 text-left transition-colors hover:border-slate-900 hover:bg-white"
      >
        <div className="flex items-center justify-between font-mono text-xs text-slate-700">
          <span>
            <span className="font-semibold text-slate-900">{citation.file}</span>
            {locator && <span className="text-slate-500"> — {locator}</span>}
          </span>
          <span className="ml-2 shrink-0 text-[11px] font-semibold text-slate-500 group-hover:text-slate-900">
            View evidence →
          </span>
        </div>
        {citation.excerpt && (
          <div className="mt-1.5 border-l-2 border-slate-300 pl-2 font-mono text-xs text-slate-600">
            {citation.excerpt}
          </div>
        )}
      </button>
    </li>
  )
}

function ReviewControls({
  f,
  onReview,
}: {
  f: Finding
  onReview: (id: string, state: ReviewState, note?: string | null) => void
}) {
  const [note, setNote] = useState(f.review_note ?? '')
  const state = f.review_state ?? 'pending'
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <button
        onClick={() => onReview(f.id, state === 'accepted' ? 'pending' : 'accepted', note || null)}
        className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
          state === 'accepted'
            ? 'bg-emerald-600 text-white'
            : 'border border-emerald-600 text-emerald-700 hover:bg-emerald-50'
        }`}
      >
        {state === 'accepted' ? '✓ Accepted' : 'Accept'}
      </button>
      <button
        onClick={() => onReview(f.id, state === 'rejected' ? 'pending' : 'rejected', note || null)}
        className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
          state === 'rejected'
            ? 'bg-slate-500 text-white'
            : 'border border-slate-400 text-slate-600 hover:bg-slate-100'
        }`}
      >
        {state === 'rejected' ? '✕ Rejected' : 'Reject'}
      </button>
      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        onBlur={() => note !== (f.review_note ?? '') && onReview(f.id, state, note || null)}
        placeholder="Add an auditor note…"
        className="min-w-[220px] flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 focus:border-slate-900 focus:outline-none"
      />
    </div>
  )
}

export function FindingsTable({
  findings,
  onChat,
  onReview,
  onOpenEvidence,
}: {
  findings: Finding[]
  onChat: (f: Finding) => void
  onReview: (id: string, state: ReviewState, note?: string | null) => void
  onOpenEvidence: (c: Citation) => void
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
          {findings.map((f) => {
            const state = f.review_state ?? 'pending'
            return (
              <>
                <tr
                  key={f.id}
                  className={`cursor-pointer border-b border-slate-100 align-top hover:bg-slate-50 ${
                    state === 'accepted'
                      ? 'bg-emerald-50/40'
                      : state === 'rejected'
                        ? 'opacity-60'
                        : ''
                  }`}
                  onClick={() => setExpanded(expanded === f.id ? null : f.id)}
                >
                  <td className="px-4 py-3 font-mono text-xs font-semibold text-slate-900">
                    {f.id}
                  </td>
                  <td className="max-w-xl px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-slate-900">{f.title}</span>
                      <ReviewBadge state={state} />
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <VerifiedBadge f={f} />
                      {f.impact_type && f.impact_type !== 'other' && (
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                          {IMPACT_LABELS[f.impact_type]}
                        </span>
                      )}
                    </div>
                    <div className={`mt-1.5 text-slate-600 ${expanded === f.id ? '' : 'line-clamp-2'}`}>
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
                  <tr key={`${f.id}-detail`} className="border-b border-slate-100 bg-slate-50/60">
                    <td />
                    <td colSpan={5} className="px-4 pt-1 pb-4" onClick={(e) => e.stopPropagation()}>
                      <p className="mb-2 text-xs font-semibold tracking-wide text-slate-500 uppercase">
                        Citations — click to inspect the source
                      </p>
                      <ul className="space-y-2">
                        {f.citations.map((c, i) => (
                          <CitationRow key={i} citation={c} onOpen={onOpenEvidence} />
                        ))}
                      </ul>
                      <ReviewControls f={f} onReview={onReview} />
                    </td>
                  </tr>
                )}
              </>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
