import { useCallback, useEffect, useState } from 'react'
import { getBatch, getImpact, reviewFinding, uploadZip } from './api'
import { ChatPanel } from './components/ChatPanel'
import { EvidenceViewer } from './components/EvidenceViewer'
import { FindingsTable } from './components/FindingsTable'
import { ImpactCard } from './components/ImpactCard'
import { Pipeline } from './components/Pipeline'
import { RuledOutList } from './components/RuledOutList'
import { UploadCard } from './components/UploadCard'
import type { BatchResult, Citation, Finding, ImpactSummary, ReviewState } from './types'

export default function App() {
  const [batchId, setBatchId] = useState<string | null>(null)
  const [batch, setBatch] = useState<BatchResult | null>(null)
  const [impact, setImpact] = useState<ImpactSummary | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [chatFinding, setChatFinding] = useState<Finding | null>(null)
  const [evidence, setEvidence] = useState<Citation | null>(null)

  const handleUpload = useCallback(async (file: File) => {
    setUploadError(null)
    try {
      const status = await uploadZip(file)
      setBatch(null)
      setImpact(null)
      setBatchId(status.batch_id)
    } catch (err) {
      setUploadError(String(err instanceof Error ? err.message : err))
    }
  }, [])

  // poll batch status until the pipeline reaches a terminal stage
  useEffect(() => {
    if (!batchId) return
    let cancelled = false
    const tick = async () => {
      try {
        const result = await getBatch(batchId)
        if (cancelled) return
        setBatch(result)
        if (result.status.stage === 'done') {
          getImpact(batchId)
            .then((i) => !cancelled && setImpact(i))
            .catch(() => {})
        }
        if (result.status.stage !== 'done' && result.status.stage !== 'error') {
          timer = window.setTimeout(tick, 1500)
        }
      } catch {
        if (!cancelled) timer = window.setTimeout(tick, 3000)
      }
    }
    let timer = window.setTimeout(tick, 300)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [batchId])

  const handleReview = useCallback(
    async (id: string, state: ReviewState, note?: string | null) => {
      if (!batchId) return
      // optimistic update
      setBatch((prev) =>
        prev
          ? {
              ...prev,
              findings: prev.findings.map((f) =>
                f.id === id ? { ...f, review_state: state, review_note: note ?? null } : f,
              ),
            }
          : prev,
      )
      try {
        await reviewFinding(batchId, id, state, note)
        const fresh = await getImpact(batchId)
        setImpact(fresh)
      } catch {
        /* keep optimistic state; next poll will reconcile */
      }
    },
    [batchId],
  )

  const stage = batch?.status.stage
  const running = batchId && stage !== 'done' && stage !== 'error'
  const ruledOut = batch?.ruled_out ?? []

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-slate-900 text-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="text-lg font-bold tracking-tight">AuditTrace</h1>
            <p className="text-xs text-slate-400">
              Every claim linked to its source — no number without a source.
            </p>
          </div>
          {batchId && (
            <button
              onClick={() => {
                setBatchId(null)
                setBatch(null)
                setImpact(null)
                setChatFinding(null)
                setEvidence(null)
              }}
              className="rounded-lg border border-slate-600 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800"
            >
              New analysis
            </button>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-10">
        {!batchId && <UploadCard onUpload={handleUpload} error={uploadError} />}

        {running && batch && <Pipeline status={batch.status} />}
        {running && !batch && <p className="text-center text-sm text-slate-500">Starting…</p>}

        {stage === 'error' && (
          <div className="mx-auto max-w-2xl rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">
            <p className="font-semibold">Pipeline failed</p>
            <p className="mt-1 font-mono text-xs">{batch?.status.error}</p>
          </div>
        )}

        {stage === 'done' && batch && (
          <div className="space-y-6">
            {impact && <ImpactCard impact={impact} />}

            <div className="space-y-4">
              <div className="flex items-end justify-between">
                <div>
                  <h2 className="text-xl font-bold text-slate-900">Findings</h2>
                  <p className="text-sm text-slate-500">
                    {batch.findings.length} finding{batch.findings.length === 1 ? '' : 's'} ·{' '}
                    {batch.documents.length} documents analyzed · batch{' '}
                    <span className="font-mono">{batch.batch_id}</span>
                  </p>
                </div>
              </div>
              <FindingsTable
                findings={batch.findings}
                onChat={setChatFinding}
                onReview={handleReview}
                onOpenEvidence={setEvidence}
              />
            </div>

            <RuledOutList items={ruledOut} />
          </div>
        )}
      </main>

      {chatFinding && batchId && (
        <ChatPanel batchId={batchId} finding={chatFinding} onClose={() => setChatFinding(null)} />
      )}
      {evidence && batchId && (
        <EvidenceViewer batchId={batchId} citation={evidence} onClose={() => setEvidence(null)} />
      )}
    </div>
  )
}
