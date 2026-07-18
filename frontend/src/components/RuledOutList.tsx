import { useState } from 'react'
import type { RuledOut } from '../types'

export function RuledOutList({ items }: { items: RuledOut[] }) {
  const [open, setOpen] = useState(false)
  if (items.length === 0) return null

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-5 py-4 text-left"
      >
        <div>
          <h3 className="text-sm font-semibold text-slate-900">
            Checked &amp; dismissed
            <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-500">
              {items.length}
            </span>
          </h3>
          <p className="text-xs text-slate-500">
            Anomalies the agent investigated and ruled out with an innocent explanation (decoy
            discipline).
          </p>
        </div>
        <span className="text-slate-400">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <ul className="divide-y divide-slate-100 border-t border-slate-100">
          {items.map((r, i) => (
            <li key={i} className="px-5 py-3">
              <div className="flex items-baseline gap-2">
                <span className="text-slate-400">✓</span>
                <span className="text-sm font-semibold text-slate-800">{r.title}</span>
                {r.check_id && (
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
                    {r.check_id}
                  </span>
                )}
              </div>
              <p className="mt-1 pl-5 text-sm text-slate-600">{r.reason}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
