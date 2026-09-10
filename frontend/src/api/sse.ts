import { getToken } from './client'
import type { DonePayload, StepEvent } from '../types'

export interface ChatHandlers {
  onStep: (ev: StepEvent) => void
  onToken: (text: string) => void
  onDone: (done: DonePayload) => void
  onError: (message: string) => void
}

/** POST /chat 的 SSE 流式消费（EventSource 不支持 POST/自定义 header，故用 fetch 流解析）。 */
export async function streamChat(
  body: { query: string; conversation_id?: number },
  handlers: ChatHandlers,
): Promise<void> {
  const token = getToken()
  const res = await fetch('/api/v1/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok || !res.body) {
    const err = (await res.json().catch(() => ({}))) as { detail?: string }
    handlers.onError(err.detail ?? `连接失败（${res.status}）`)
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      dispatchBlock(block, handlers)
    }
  }
}

function dispatchBlock(block: string, handlers: ChatHandlers): void {
  let event = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7).trim()
    else if (line.startsWith('data: ')) data += line.slice(6)
  }
  if (!data) return
  let payload: unknown
  try {
    payload = JSON.parse(data)
  } catch {
    return
  }
  switch (event) {
    case 'step':
      handlers.onStep(payload as StepEvent)
      break
    case 'token':
      handlers.onToken((payload as { text: string }).text)
      break
    case 'done':
      handlers.onDone(payload as DonePayload)
      break
    case 'error':
      handlers.onError((payload as { message: string }).message)
      break
  }
}
