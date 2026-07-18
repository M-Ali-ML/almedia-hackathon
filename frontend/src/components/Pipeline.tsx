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
    <div className="mx-auto max-w-2xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
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
                      ? 'bg-emerald-600 text-white'
                      : isActive
                        ? 'animate-pulse bg-slate-900 text-white'
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
                  className={`mx-2 mb-6 h-0.5 flex-1 ${isDone ? 'bg-emerald-600' : 'bg-slate-200'}`}
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
