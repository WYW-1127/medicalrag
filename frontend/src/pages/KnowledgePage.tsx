import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ChunkSample, IngestJobInfo, KbDocument } from '../types'
import { Badge, Button, Card } from '../components/ui'

interface DocumentsResponse {
  documents: KbDocument[]
  last_ingest_job: IngestJobInfo | null
}

export default function KnowledgePage() {
  const [data, setData] = useState<DocumentsResponse>({ documents: [], last_ingest_job: null })
  const [chunks, setChunks] = useState<Record<string, ChunkSample[]>>({})
  const [expanded, setExpanded] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const refresh = useCallback(async () => {
    try {
      setData(await api<DocumentsResponse>('/documents'))
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '加载失败')
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  async function toggleChunks(doc: KbDocument) {
    const hash = doc.doc_hash
    if (expanded === hash) {
      setExpanded(null)
      return
    }
    setExpanded(hash)
    if (!chunks[hash]) {
      try {
        const rows = await api<ChunkSample[]>(`/documents/${hash}/chunks?k=3`)
        setChunks((prev) => ({ ...prev, [hash]: rows }))
      } catch (err) {
        setMessage(err instanceof Error ? err.message : 'chunk 加载失败')
      }
    }
  }

  async function triggerIngest() {
    setBusy(true)
    setMessage('')
    try {
      const res = await api<{ started: boolean; detail?: string }>('/admin/ingest', {
        method: 'POST',
        body: JSON.stringify({ dir: '../data/raw' }),
      })
      setMessage(res.started ? '入库任务已启动，稍后刷新查看' : (res.detail ?? '任务未启动'))
    } catch (err) {
      setMessage(err instanceof Error ? err.message : '触发失败')
    } finally {
      setBusy(false)
    }
  }

  const job = data.last_ingest_job
  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">知识库管理</h1>
            <p className="mt-0.5 text-sm text-slate-500">
              共 {data.documents.length} 份文档、
              {data.documents.reduce((s, d) => s + d.chunk_count, 0)} 个切片
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="ghost" onClick={refresh}>
              刷新
            </Button>
            <Button onClick={triggerIngest} disabled={busy}>
              {busy ? '提交中…' : '触发入库'}
            </Button>
          </div>
        </div>

        {job && (
          <Card className="flex items-center gap-3 px-4 py-2.5 text-sm">
            <span className="text-slate-500">最近入库任务：</span>
            <Badge
              tone={job.status === 'completed' ? 'green' : job.status === 'failed' ? 'rose' : 'amber'}
            >
              {job.status}
            </Badge>
            <span className="text-slate-600">
              {job.processed_docs}/{job.total_docs} 文档 · {job.total_chunks} chunks
            </span>
            {job.error && <span className="truncate text-xs text-rose-600">{job.error}</span>}
          </Card>
        )}

        {message && (
          <div className="rounded-lg border border-primary-200 bg-primary-50 px-4 py-2 text-sm text-primary-800">
            {message}
          </div>
        )}

        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs text-slate-500">
                <th className="px-4 py-2.5 font-medium">文档</th>
                <th className="px-4 py-2.5 font-medium">科室</th>
                <th className="px-4 py-2.5 font-medium">类型</th>
                <th className="px-4 py-2.5 font-medium">切片数</th>
                <th className="px-4 py-2.5 font-medium">更新时间</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {data.documents.map((d) => (
                <>
                  <tr key={d.doc_hash} className="border-b border-slate-100 hover:bg-slate-50">
                    <td className="max-w-[280px] truncate px-4 py-2.5 font-medium text-slate-700" title={d.source}>
                      {d.title || d.source}
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge tone="cyan">{d.department}</Badge>
                    </td>
                    <td className="px-4 py-2.5 text-slate-500">{d.doc_type}</td>
                    <td className="px-4 py-2.5 tabular-nums text-slate-600">{d.chunk_count}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-400">
                      {new Date(d.updated_at).toLocaleString('zh-CN')}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <button
                        className="text-xs text-primary-700 hover:underline"
                        onClick={() => toggleChunks(d)}
                      >
                        {expanded === d.doc_hash ? '收起' : '查看切片'}
                      </button>
                    </td>
                  </tr>
                  {expanded === d.doc_hash && (
                    <tr key={`${d.doc_hash}-detail`} className="border-b border-slate-100 bg-slate-50/60">
                      <td colSpan={6} className="px-4 py-3">
                        {(chunks[d.doc_hash] ?? []).length === 0 && (
                          <p className="text-xs text-slate-400">加载中…</p>
                        )}
                        <div className="space-y-2">
                          {(chunks[d.doc_hash] ?? []).map((c) => (
                            <div key={c.chunk_id} className="rounded-lg border border-slate-200 bg-white p-2.5">
                              <p className="mb-1 text-[11px] text-slate-400">
                                {c.chunk_id} ｜ {c.section_path || '无章节'}
                              </p>
                              <p className="max-h-28 overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-slate-600">
                                {c.text}
                              </p>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
              {data.documents.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-sm text-slate-400">
                    知识库为空——把资料放入 data/raw/ 后点「触发入库」
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  )
}
