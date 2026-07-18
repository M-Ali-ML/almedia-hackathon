import { useCallback, useRef, useState } from 'react'

export function UploadCard({ onUpload, error }: { onUpload: (f: File) => void; error?: string | null }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const handleFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0]
      if (file) onUpload(file)
    },
    [onUpload],
  )

  return (
    <div className="mx-auto max-w-2xl pt-4">
      <div className="mb-8 text-center">
        <p className="mb-3 text-xs font-bold tracking-[0.18em] text-cyan-700 uppercase">Forensic audit workspace</p>
        <h2 className="text-3xl font-bold tracking-[-0.045em] text-slate-950 sm:text-4xl">
          Trace risk back to evidence.
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-500 sm:text-base">
          Analyze an accounting dossier for suspicious journal entries, control failures, and cross-document anomalies.
        </p>
      </div>
      <div
        className={`group cursor-pointer rounded-3xl border bg-white/90 p-10 text-center shadow-[0_18px_60px_-30px_rgba(15,23,42,0.35)] transition-all sm:p-12 ${
          dragging
            ? 'border-cyan-500 bg-cyan-50/70 ring-4 ring-cyan-100'
            : 'border-slate-200 hover:-translate-y-0.5 hover:border-cyan-300 hover:shadow-[0_24px_70px_-30px_rgba(8,145,178,0.35)]'
        }`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          handleFiles(e.dataTransfer.files)
        }}
      >
        <div className="brand-mark mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl text-white shadow-lg shadow-cyan-950/15 transition-transform group-hover:scale-105">
          <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
            <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M5 14.5v3A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5v-3" strokeLinecap="round" />
          </svg>
        </div>
        <p className="text-lg font-bold tracking-tight text-slate-950">Upload accounting dossier</p>
        <p className="mt-1.5 text-sm text-slate-500">
          Drop a GDPdU ZIP here or <span className="font-semibold text-cyan-700">browse files</span>
        </p>
        <p className="mt-4 text-xs text-slate-400">ZIP format · source files remain traceable throughout the audit</p>
        <input
          ref={inputRef}
          type="file"
          accept=".zip"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>
      {error && (
        <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}
    </div>
  )
}
