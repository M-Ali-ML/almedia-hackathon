import type { BatchStatus, Stage } from '../types'

const STEPS: { stage: Stage; label: string }[] = [
  { stage: 'extracting', label: 'Extracting' },
  { stage: 'ingesting', label: 'Ingesting' },
  { stage: 'building_context', label: 'Pre-analyzing' },
  { stage: 'analyzing', label: 'Analyzing' },
  { stage: 'done', label: 'Done' },
]

export function Pipeline({ status }: { status: BatchStatus }) {
  const currentIdx = STEPS.findIndex((s) => s.stage === status.stage)
  return (
    <div className="mx-auto max-w-3xl rounded-3xl border border-slate-200 bg-white/90 p-8 shadow-[0_18px_60px_-30px_rgba(15,23,42,0.28)] sm:p-10">
      <div className="mb-8 text-center">
        <p className="text-xs font-bold tracking-[0.16em] text-cyan-700 uppercase">AudiTrace analysis</p>
        <h2 className="mt-2 text-xl font-bold tracking-tight text-slate-950">Tracing anomalies across the dossier</h2>
      </div>
      <div className="flex items-center justify-between">
        {STEPS.map((step, i) => {
          const isDone = currentIdx > i || status.stage === 'done'
          const isActive = currentIdx === i && status.stage !== 'done'
          return (
            <div key={step.stage} className="flex flex-1 items-center last:flex-none">
              <div className="flex flex-col items-center gap-2">
                <div
                  className={`flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold transition-colors ${
                    isDone
                      ? 'bg-emerald-500 text-white shadow-sm shadow-emerald-200'
                      : isActive
                        ? 'animate-pulse bg-cyan-600 text-white shadow-md shadow-cyan-200'
                        : 'bg-slate-200 text-slate-500'
                  }`}
                >
                  {isDone ? '✓' : i + 1}
                </div>
                <span
                  className={`text-xs font-semibold ${isActive ? 'text-slate-900' : 'text-slate-500'}`}
                >
                  {step.label}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div
                  className={`mx-2 mb-6 h-0.5 flex-1 ${isDone ? 'bg-emerald-500' : 'bg-slate-200'}`}
                />
              )}
            </div>
          )
        })}
      </div>
      {status.detail && <p className="mt-6 text-center text-sm text-slate-500">{status.detail}</p>}
      {status.stage === 'analyzing' && (
        <p className="mt-2 text-center text-xs text-slate-400">
          The auditor agent is querying the dossier — this can take a few minutes.
        </p>
      )}
    </div>
  )
}
