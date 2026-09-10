import type { MouseEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeRaw from 'rehype-raw'
import remarkGfm from 'remark-gfm'
import type { Citation, Message } from '../types'
import CitationCard from './CitationCard'

/** 流式中的 assistant 气泡（token 逐字追加 + 已完成步骤数）。 */
export function StreamingBubble({ text, stepCount }: { text: string; stepCount: number }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[92%] rounded-2xl rounded-tl-sm border border-primary-100 bg-white px-4 py-3 shadow-sm">
        <p className="mb-1 flex items-center gap-1.5 text-xs text-primary-600">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary-500" />
          思考中 · 已完成 {stepCount} 步
        </p>
        {text ? (
          <div className="md-body text-sm">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
          </div>
        ) : (
          <div className="flex gap-1 py-1">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary-300"
                style={{ animationDelay: `${i * 150}ms` }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function withCitationHtml(text: string, hasCitations: boolean): string {
  if (!hasCitations) return text
  return text.replace(
    /\[(\d+)\]/g,
    (_m, n: string) =>
      `<sup class="cite" data-n="${n}" title="引用 ${n}，见下方参考来源">${n}</sup>`,
  )
}

function onAssistantClick(e: MouseEvent<HTMLDivElement>): void {
  const target = e.target as HTMLElement
  if (target.classList?.contains('cite')) {
    document.getElementById(`cite-${target.dataset.n}`)?.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest',
    })
  }
}

export function MessageBubble({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-tr-sm bg-primary-700 px-4 py-2.5 text-sm text-white">
          {message.content}
        </div>
      </div>
    )
  }
  const citations = message.citations ?? []
  return (
    <div className="flex justify-start">
      <div className="max-w-[92%] rounded-2xl rounded-tl-sm border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <div className="md-body text-sm" onClick={onAssistantClick}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
            {withCitationHtml(message.content, citations.length > 0)}
          </ReactMarkdown>
        </div>
        {citations.length > 0 && (
          <div className="mt-3 border-t border-slate-100 pt-2">
            <p className="mb-1.5 text-xs font-medium text-slate-500">
              参考来源（{citations.length}）
            </p>
            <div className="space-y-1.5">
              {citations.map((c) => (
                <div key={`${c.no}-${c.chunk_id}`} id={`cite-${c.no}`}>
                  <CitationCard cite={c} />
                </div>
              ))}
            </div>
          </div>
        )}
        {message.latency_ms != null && (
          <p className="mt-2 text-right text-[11px] text-slate-300">
            {(message.latency_ms / 1000).toFixed(1)}s
          </p>
        )}
      </div>
    </div>
  )
}

/** 把 done 结果转成 Message（供消息列表追加）。 */
export function assistantFromDone(
  content: string,
  citations: Citation[],
  latencyMs: number,
): Message {
  return {
    id: -1,
    role: 'assistant',
    content,
    citations,
    latency_ms: latencyMs,
    created_at: new Date().toISOString(),
  }
}
