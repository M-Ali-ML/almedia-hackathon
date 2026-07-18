import { useCallback, useEffect, useState } from 'react'
import { getBatch, getImpact, reviewFinding, uploadZip } from './api'
import { ChatPanel } from './components/ChatPanel'
import { EvidenceViewer } from './components/EvidenceViewer'
import { FindingsTable } from './components/FindingsTable'
import { ImpactCard } from './components/ImpactCard'
import { Pipeline } from './components/Pipeline'
import { PreAnalysisOverlay } from './components/PreAnalysisOverlay'
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
  const [preAnalysisOpen, setPreAnalysisOpen] = useState(false)

  const handleUpload = useCallback(async (file: File) => {
    setUploadError(null)
    try {
      const status = await uploadZip(file)
      setBatch(null)
      setImpact(null)
      setPreAnalysisOpen(false)
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

  const resetAnalysis = () => {
    setBatchId(null)
    setBatch(null)
    setImpact(null)
    setChatFinding(null)
    setEvidence(null)
    setPreAnalysisOpen(false)
  }

  return (
    <div className="app-shell min-h-screen">
      <header className="border-b border-white/10 bg-[#071323]/95 text-white shadow-[0_1px_0_rgba(255,255,255,0.03)] backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="brand-mark flex h-10 w-10 items-center justify-center rounded-xl" aria-hidden="true">
              <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none">
                <path d="M5 17.5 10.5 5h3L19 17.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M7.3 13.2h9.4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                <circle cx="18.8" cy="6" r="1.7" fill="currentColor" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-[-0.035em]">Audi<span className="text-cyan-300">Trace</span></h1>
              <p className="text-[11px] font-medium tracking-wide text-slate-400">
                Evidence-led fraud intelligence
              </p>
            </div>
          </div>
          {batchId && (
            <div className="flex items-center gap-2">
              {batch?.global_context && (
                <button
                  type="button"
                  onClick={() => setPreAnalysisOpen(true)}
                  className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:border-cyan-300/30 hover:bg-white/10 hover:text-white"
                  aria-label="Open pre-analysis overview"
                  title="Pre-analysis overview"
                >
                  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                    <path d="M4 5.5h16v13H4z" />
                    <path d="M7 15l3-3 2.5 2 4.5-5" />
                    <path d="M7 8h3" />
                  </svg>
                  Pre-analysis
                </button>
              )}
              <button
                onClick={resetAnalysis}
                className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:border-cyan-300/30 hover:bg-white/10 hover:text-white"
              >
                New analysis
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 py-10 sm:px-6 sm:py-12">
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
                  <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[10px] font-bold tracking-[0.12em] text-emerald-700 uppercase">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Analysis complete
                  </div>
                  <h2 className="text-2xl font-bold tracking-[-0.035em] text-slate-950">Audit findings</h2>
                  <p className="mt-1 text-sm text-slate-500">
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
      {preAnalysisOpen && batch && (
        <PreAnalysisOverlay batch={batch} onClose={() => setPreAnalysisOpen(false)} />
      )}
    </div>
  )
}
