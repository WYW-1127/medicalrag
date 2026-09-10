import type { Citation } from '../types'
import { Badge } from './ui'

/** 参考来源卡片：编号、来源文档、章节、页码，hover/展开显示 chunk 原文。 */
export default function CitationCard({ cite }: { cite: Citation }) {
  return (
    <details className="group rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 open:bg-white">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-xs text-slate-600">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary-100 text-[11px] font-semibold text-primary-800">
          {cite.no}
        </span>
        <span className="truncate font-medium text-slate-700">{cite.source}</span>
        {cite.section_path && (
          <span className="truncate text-slate-400">｜{cite.section_path}</span>
        )}
        {cite.page > 0 && <Badge tone="slate">P{cite.page}</Badge>}
        <span className="ml-auto text-slate-400 group-open:rotate-180">▾</span>
      </summary>
      <blockquote className="mt-2 max-h-40 overflow-y-auto border-l-2 border-primary-200 pl-3 text-xs leading-relaxed text-slate-600 whitespace-pre-wrap">
        {cite.text}
      </blockquote>
    </details>
  )
}
