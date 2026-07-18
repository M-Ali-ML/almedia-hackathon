import type { ImpactSummary } from '../types'

const eur = (v?: number | null) =>
  v == null ? '—' : v.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })

function Stat({
  label,
  value,
  tone = 'default',
  sub,
}: {
  label: string
  value: string
  tone?: 'default' | 'red' | 'emerald' | 'amber'
  sub?: string
}) {
  const valueCls =
    tone === 'red'
      ? 'text-red-600'
      : tone === 'emerald'
        ? 'text-emerald-600'
        : tone === 'amber'
          ? 'text-amber-600'
          : 'text-slate-900'
  return (
    <div className="flex-1">
      <p className="text-xs font-semibold tracking-wide text-slate-400 uppercase">{label}</p>
      <p className={`mt-1 text-2xl font-bold tabular-nums ${valueCls}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
    </div>
  )
}

export function ImpactCard({ impact }: { impact: ImpactSummary }) {
  const hasProfit = impact.reported_profit_eur != null
  const overstatementPct =
    hasProfit && impact.reported_profit_eur
      ? (impact.profit_overstatement_eur / impact.reported_profit_eur) * 100
      : null
  const reviewed = impact.accepted_count + impact.rejected_count

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-wide text-slate-500 uppercase">
          Financial impact
        </h2>
        <span className="text-xs text-slate-400">
          {impact.accepted_count} accepted · {impact.pending_count} pending
          {impact.rejected_count > 0 ? ` · ${impact.rejected_count} rejected` : ''}
        </span>
      </div>

      {/* Hero: total exposure identified across all non-rejected findings */}
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3 rounded-xl bg-slate-900 px-5 py-4 text-white">
        <div>
          <p className="text-xs font-semibold tracking-wide text-slate-400 uppercase">
            Total exposure identified
          </p>
          <p className="mt-1 text-3xl font-bold tabular-nums">{eur(impact.total_exposure_eur)}</p>
          <p className="mt-0.5 text-xs text-slate-400">
            across {impact.finding_count} finding{impact.finding_count === 1 ? '' : 's'}
            {impact.rejected_count > 0 ? ` (${impact.rejected_count} rejected, excluded)` : ''}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs font-semibold tracking-wide text-emerald-300 uppercase">
            Confirmed by auditor
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-emerald-400">
            {eur(impact.confirmed_exposure_eur)}
          </p>
          <p className="mt-0.5 text-xs text-slate-400">
            {reviewed}/{impact.finding_count} reviewed
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-6">
        <Stat
          label="Cash misappropriation"
          value={eur(impact.cash_misappropriation_eur)}
          tone={impact.cash_misappropriation_eur > 0 ? 'red' : 'default'}
        />
        <Stat
          label="Profit overstatement"
          value={eur(impact.profit_overstatement_eur)}
          tone={impact.profit_overstatement_eur > 0 ? 'red' : 'default'}
          sub={overstatementPct != null ? `${overstatementPct.toFixed(1)}% of reported profit` : undefined}
        />
        <Stat
          label="Reported profit"
          value={eur(impact.reported_profit_eur)}
          sub={hasProfit ? 'Jahresüberschuss (draft)' : 'not found in dossier'}
        />
        <Stat
          label="Corrected profit"
          value={eur(impact.corrected_profit_eur)}
          tone={impact.profit_overstatement_eur > 0 ? 'emerald' : 'default'}
          sub={
            impact.profit_overstatement_eur > 0
              ? 'after reversing overstatements'
              : 'no P&L overstatement found'
          }
        />
        <Stat
          label="Control breaches"
          value={String(impact.control_breach_count)}
          tone={impact.control_breach_count > 0 ? 'amber' : 'default'}
          sub="policy / SoD violations"
        />
      </div>

      {impact.accepted_count === 0 && impact.finding_count > 0 && (
        <p className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
          Headline figures reflect all findings the agent surfaced. Accept a finding to move it into{' '}
          <span className="font-semibold text-emerald-700">confirmed</span>, or reject a false
          positive to remove it from the totals.
        </p>
      )}
    </div>
  )
}
