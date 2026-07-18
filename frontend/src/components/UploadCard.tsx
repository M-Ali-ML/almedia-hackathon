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
    <div className="mx-auto max-w-xl">
      <div
        className={`cursor-pointer rounded-2xl border-2 border-dashed bg-white p-12 text-center shadow-sm transition-colors ${
          dragging ? 'border-slate-900 bg-slate-100' : 'border-slate-300 hover:border-slate-500'
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
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-slate-900 text-xl text-white">
          ⇪
        </div>
        <p className="text-lg font-semibold text-slate-900">Upload dossier ZIP</p>
        <p className="mt-1 text-sm text-slate-500">
          Drop the GDPdU export zip here or click to browse
        </p>
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
