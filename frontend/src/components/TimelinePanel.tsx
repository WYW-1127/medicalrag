import type { StepEvent } from '../types'

const NODE_LABELS: Record<string, string> = {
  analyze: '意图分析',
  rewrite: '查询改写',
  decompose: '问题分解',
  retrieve: '混合检索',
  grade: '相关性反思',
  generate: '生成回答',
  verify: '引用校验',
  fallback: '拒答兜底',
  safe_reply: '安全回复',
}

/** Agentic 检索时间线：step 事件实时追加，最新节点高亮。 */
export default function TimelinePanel({ steps, running }: { steps: StepEvent[]; running: boolean }) {
  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-l border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
        <h2 className="text-sm font-semibold text-slate-700">检索时间线</h2>
        {running && (
          <span className="flex items-center gap-1 text-xs text-primary-700">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary-500" />
            运行中
          </span>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {steps.length === 0 && (
          <p className="px-2 py-6 text-center text-xs text-slate-400">
            提问后这里会实时展示 Agentic 检索的每一步
          </p>
        )}
        <ol className="space-y-2">
          {steps.map((s, i) => {
            const isLast = i === steps.length - 1
            return (
              <li
                key={`${s.name}-${i}`}
                className={`rounded-lg border p-2.5 text-xs transition-colors ${
                  running && isLast
                    ? 'border-primary-300 bg-primary-50'
                    : 'border-slate-100 bg-slate-50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5 font-medium text-slate-700">
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${running && isLast ? 'bg-primary-500' : 'bg-emerald-500'}`}
                    />
                    {NODE_LABELS[s.name] ?? s.name}
                  </span>
                  <span className="tabular-nums text-slate-400">{Math.round(s.ms)}ms</span>
                </div>
                {s.detail && (
                  <p className="mt-1 break-all pl-3 text-[11px] leading-relaxed text-slate-500">
                    {s.detail}
                  </p>
                )}
              </li>
            )
          })}
        </ol>
      </div>
    </aside>
  )
}
