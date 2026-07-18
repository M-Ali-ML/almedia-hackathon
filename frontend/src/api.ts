import type { BatchResult, BatchStatus, ChatMessage, Finding } from './types'

export async function uploadZip(file: File): Promise<BatchStatus> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch('/api/batches', { method: 'POST', body: form })
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? res.statusText)
  return res.json()
}

export async function getBatch(batchId: string): Promise<BatchResult> {
  const res = await fetch(`/api/batches/${batchId}`)
  if (!res.ok) throw new Error(res.statusText)
  return res.json()
}

export type ChatEvent =
  | { type: 'delta'; text: string }
  | { type: 'activity'; text: string }
  | { type: 'error'; message: string }

/**
 * Minimal AG-UI client: POSTs a RunAgentInput to the backend and yields
 * text deltas from the SSE stream. The finding and batch id travel as
 * AG-UI shared state so the backend agent is scoped to them.
 */
export async function* streamChat(opts: {
  batchId: string
  finding: Finding
  messages: ChatMessage[]
  signal?: AbortSignal
}): AsyncGenerator<ChatEvent> {
  const body = {
    threadId: `finding-${opts.finding.id}-${opts.batchId}`,
    runId: crypto.randomUUID(),
    state: { batch_id: opts.batchId, finding: opts.finding },
    messages: opts.messages.map((m) => ({ id: m.id, role: m.role, content: m.content })),
    tools: [],
    context: [],
    forwardedProps: {},
  }
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal: opts.signal,
  })
  if (!res.ok || !res.body) {
    yield { type: 'error', message: `chat request failed: ${res.status} ${res.statusText}` }
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      for (const line of block.split('\n')) {
        if (!line.startsWith('data:')) continue
        let event: Record<string, unknown>
        try {
          event = JSON.parse(line.slice(5).trim())
        } catch {
          continue
        }
        switch (event.type) {
          case 'TEXT_MESSAGE_CONTENT':
            yield { type: 'delta', text: String(event.delta ?? '') }
            break
          case 'TOOL_CALL_START':
            yield { type: 'activity', text: `running ${String(event.toolCallName ?? 'tool')}…` }
            break
          case 'RUN_ERROR':
            yield { type: 'error', message: String(event.message ?? 'agent error') }
            break
        }
      }
    }
  }
}
