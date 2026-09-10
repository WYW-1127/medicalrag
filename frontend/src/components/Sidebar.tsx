import type { Conversation } from '../types'

export default function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
}: {
  conversations: Conversation[]
  activeId: number | null
  onSelect: (id: number) => void
  onNew: () => void
}) {
  return (
    <aside className="flex h-full w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="p-3">
        <button
          onClick={onNew}
          className="w-full rounded-lg border border-primary-200 bg-primary-50 py-2 text-sm font-medium text-primary-800 transition-colors hover:bg-primary-100"
        >
          ＋ 新对话
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {conversations.length === 0 && (
          <p className="px-2 py-4 text-center text-xs text-slate-400">暂无历史会话</p>
        )}
        <ul className="space-y-1">
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => onSelect(c.id)}
                className={`w-full truncate rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                  c.id === activeId
                    ? 'bg-primary-100 font-medium text-primary-900'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
                title={c.title}
              >
                {c.title || '新对话'}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  )
}
