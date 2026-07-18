import { useEffect, useRef, useState } from 'react'
import { streamChat } from '../api'
import type { ChatMessage, Finding } from '../types'

export function ChatPanel({
  batchId,
  finding,
  onClose,
}: {
  batchId: string
  finding: Finding
  onClose: () => void
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [activity, setActivity] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages, activity])

  // reset the conversation when switching findings
  useEffect(() => {
    setMessages([])
    setInput('')
  }, [finding.id])

  async function send() {
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    setBusy(true)
    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: text }
    const history = [...messages, userMsg]
    setMessages(history)
    const assistantId = crypto.randomUUID()
    let assistantText = ''
    try {
      for await (const event of streamChat({ batchId, finding, messages: history })) {
        if (event.type === 'delta') {
          setActivity(null)
          assistantText += event.text
        } else if (event.type === 'activity') {
          setActivity(event.text)
        } else if (event.type === 'error') {
          assistantText += `\n[error: ${event.message}]`
        }
        const current = assistantText
        setMessages([...history, { id: assistantId, role: 'assistant', content: current }])
      }
    } catch (err) {
      setMessages([
        ...history,
        { id: assistantId, role: 'assistant', content: `[request failed: ${String(err)}]` },
      ])
    } finally {
      setActivity(null)
      setBusy(false)
    }
  }

  return (
    <aside className="fixed inset-y-0 right-0 z-20 flex w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-2xl">
      <header className="flex items-start justify-between border-b border-slate-200 p-4">
        <div>
          <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
            Chat · finding <span className="font-mono">{finding.id}</span>
          </p>
          <p className="mt-1 line-clamp-2 text-sm font-semibold text-slate-900">{finding.title}</p>
        </div>
        <button
          onClick={onClose}
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          aria-label="Close chat"
        >
          ✕
        </button>
      </header>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="text-sm text-slate-400">
            Ask follow-up questions about this finding, e.g. “show me all payments to this vendor”.
          </p>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm whitespace-pre-wrap ${
              m.role === 'user'
                ? 'ml-auto bg-slate-900 text-white'
                : 'mr-auto border border-slate-200 bg-slate-50 text-slate-800'
            }`}
          >
            {m.content || '…'}
          </div>
        ))}
        {activity && <p className="animate-pulse font-mono text-xs text-slate-400">{activity}</p>}
      </div>

      <footer className="border-t border-slate-200 p-3">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Ask about this finding…"
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-slate-900"
            disabled={busy}
          />
          <button
            onClick={send}
            disabled={busy || !input.trim()}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
          >
            {busy ? '…' : 'Send'}
          </button>
        </div>
      </footer>
    </aside>
  )
}
