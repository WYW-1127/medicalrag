import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Heartbeat } from '@phosphor-icons/react'
import { api } from '../api/client'
import { streamChat } from '../api/sse'
import type { Conversation, DonePayload, Message, StepEvent } from '../types'
import Sidebar from '../components/Sidebar'
import TimelinePanel from '../components/TimelinePanel'
import { MessageBubble, StreamingBubble, assistantFromDone } from '../components/MessageList'

export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [steps, setSteps] = useState<StepEvent[]>([])
  const [error, setError] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await api<Conversation[]>('/conversations'))
    } catch {
      /* 401 已由 client 处理跳转 */
    }
  }, [])

  useEffect(() => {
    refreshConversations()
  }, [refreshConversations])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamText, steps])

  async function selectConversation(id: number) {
    setActiveId(id)
    setError('')
    setSteps([])
    try {
      setMessages(await api<Message[]>(`/conversations/${id}/messages`))
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    }
  }

  function newConversation() {
    setActiveId(null)
    setMessages([])
    setSteps([])
    setError('')
  }

  async function send(e: FormEvent) {
    e.preventDefault()
    const query = input.trim()
    if (!query || busy) return
    setInput('')
    setBusy(true)
    setError('')
    setStreamText('')
    setSteps([])
    setMessages((prev) => [
      ...prev,
      {
        id: -Date.now(),
        role: 'user',
        content: query,
        citations: null,
        latency_ms: null,
        created_at: new Date().toISOString(),
      },
    ])

    let finalText = ''
    let donePayload: DonePayload | null = null
    try {
      await streamChat(
        { query, ...(activeId ? { conversation_id: activeId } : {}) },
        {
          onStep: (ev) => setSteps((prev) => [...prev, ev]),
          onToken: (t) => {
            finalText += t
            setStreamText(finalText)
          },
          onDone: (d) => {
            donePayload = d
          },
          onError: (msg) => setError(msg),
        },
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : '连接中断')
    }

    if (donePayload) {
      const d = donePayload as DonePayload
      setStreamText('')
      setMessages((prev) => [
        ...prev,
        assistantFromDone(finalText, d.citations, d.latency_ms),
      ])
      if (!activeId) setActiveId(d.conversation_id)
      refreshConversations()
    }
    setBusy(false)
  }

  return (
    <div className="flex h-full">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={selectConversation}
        onNew={newConversation}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          {messages.length === 0 && !streamText && !busy && (
            <div className="mx-auto max-w-md px-4 py-16 text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-700 text-white">
                <Heartbeat size={30} weight="bold" />
              </div>
              <h1 className="text-lg font-semibold text-slate-800">医学知识问答</h1>
              <p className="mt-2 text-sm leading-relaxed text-slate-500">
                基于心血管临床指南与药品说明书知识库的检索增强问答，
                支持对比型问题与多轮追问，回答附可溯源引用。
              </p>
              <div className="mt-5 space-y-2 text-left">
                {['高血压的诊断标准是什么？', '二甲双胍适合什么样的糖尿病人？', '哮喘急性发作如何处理？'].map(
                  (q) => (
                    <button
                      key={q}
                      onClick={() => {
                        setInput(q)
                      }}
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 transition-colors hover:border-primary-300 hover:text-primary-800"
                    >
                      {q}
                    </button>
                  ),
                )}
              </div>
            </div>
          )}
          <div className="mx-auto max-w-3xl space-y-4">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {busy && <StreamingBubble text={streamText} stepCount={steps.length} />}
            {error && (
              <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                {error}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        </div>
        <form
          onSubmit={send}
          className="shrink-0 border-t border-slate-200 bg-white px-6 py-3"
        >
          <div className="mx-auto flex max-w-3xl items-center gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="输入医学问题，如：妊娠期高血压如何用药？"
              className="flex-1 rounded-xl border border-slate-300 px-4 py-2.5 text-sm outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-100"
              disabled={busy}
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              className="rounded-xl bg-primary-700 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-800 disabled:bg-primary-300"
            >
              {busy ? '回答中…' : '发送'}
            </button>
          </div>
        </form>
      </main>
      <TimelinePanel steps={steps} running={busy} />
    </div>
  )
}
