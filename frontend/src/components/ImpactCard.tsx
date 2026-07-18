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
  tone?: 'default' | 'red' | 'emerald'
  sub?: string
}) {
  const valueCls =
    tone === 'red' ? 'text-red-600' : tone === 'emerald' ? 'text-emerald-600' : 'text-slate-900'
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

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-wide text-slate-500 uppercase">
          Financial impact
        </h2>
        <span className="text-xs text-slate-400">
          {impact.accepted_count} accepted · {impact.pending_count} pending review
        </span>
      </div>

      <div className="flex flex-wrap gap-6">
        <Stat
          label="Reported profit"
          value={eur(impact.reported_profit_eur)}
          sub={hasProfit ? 'Jahresüberschuss (draft)' : 'not found in dossier'}
        />
        <Stat
          label="Profit overstatement"
          value={eur(impact.profit_overstatement_eur)}
          tone={impact.profit_overstatement_eur > 0 ? 'red' : 'default'}
          sub={overstatementPct != null ? `${overstatementPct.toFixed(1)}% of reported` : undefined}
        />
        <Stat
          label="Corrected profit"
          value={eur(impact.corrected_profit_eur)}
          tone={impact.profit_overstatement_eur > 0 ? 'emerald' : 'default'}
          sub="after accepted corrections"
        />
        <Stat
          label="Cash misappropriation"
          value={eur(impact.cash_misappropriation_eur)}
          tone={impact.cash_misappropriation_eur > 0 ? 'red' : 'default'}
          sub={
            impact.control_breach_count > 0
              ? `+ ${impact.control_breach_count} control breach${impact.control_breach_count === 1 ? '' : 'es'}`
              : undefined
          }
        />
      </div>

      {impact.accepted_count === 0 && (
        <p className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
          Accept findings below to roll their impact into the corrected profit. Total flagged
          exposure across all findings: <span className="font-semibold">{eur(impact.total_flagged_eur)}</span>.
        </p>
      )}
    </div>
  )
}
