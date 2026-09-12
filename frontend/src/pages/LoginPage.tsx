import type { FormEvent } from 'react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Heartbeat, ShieldCheck, Quotes, TextAa } from '@phosphor-icons/react'
import type { Icon } from '@phosphor-icons/react'
import { api, setToken } from '../api/client'
import { Button, FieldLabel, Input } from '../components/ui'

const CAPABILITIES: Array<{ icon: Icon; title: string; desc: string }> = [
  {
    icon: Quotes,
    title: '可溯源引用',
    desc: '每个关键结论都标注出处，附指南章节与页码',
  },
  {
    icon: ShieldCheck,
    title: '证据不足即拒答',
    desc: '检索反思与引用校验双层把关，不在缺乏依据时编造',
  },
  {
    icon: TextAa,
    title: '口语化提问',
    desc: '支持症状的日常说法，自动对齐医学术语后检索',
  },
]

export default function LoginPage() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      if (mode === 'register') {
        await api<{ username: string }>('/auth/register', {
          method: 'POST',
          body: JSON.stringify({ username, password }),
        })
      }
      const { access_token } = await api<{ access_token: string }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
      setToken(access_token)
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-[100dvh] grid-cols-1 lg:grid-cols-[5fr_4fr]">
      {/* 品牌面板：桌面显示，移动端隐藏 */}
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-primary-800 p-12 text-white lg:flex">
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.08]"
          style={{
            backgroundImage:
              'radial-gradient(circle at 1px 1px, white 1px, transparent 0)',
            backgroundSize: '28px 28px',
          }}
        />
        <div className="relative flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/15">
            <Heartbeat size={22} weight="bold" />
          </span>
          <span className="text-lg font-semibold tracking-tight">MedicalRAG</span>
        </div>
        <div className="relative max-w-md">
          <h1 className="text-3xl leading-snug font-semibold tracking-tight">
            心血管专科
            <br />
            医学知识问答助手
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-primary-100">
            基于 10 份临床指南与 9 类常用心血管药品说明书构建，
            回答附可溯源引用，急症问题自动引导就医。
          </p>
          <ul className="mt-10 space-y-5">
            {CAPABILITIES.map(({ icon: IconCmp, title, desc }) => (
              <li key={title} className="flex gap-3.5">
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/12">
                  <IconCmp size={17} />
                </span>
                <div>
                  <p className="text-sm font-medium">{title}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-primary-200">{desc}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-primary-200/80">
          内容基于公开医学资料，仅供参考，不构成诊疗建议
        </p>
      </aside>

      {/* 表单区 */}
      <main className="flex items-center justify-center bg-slate-50 p-6">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-primary-700 text-white">
              <Heartbeat size={24} weight="bold" />
            </div>
            <h1 className="text-lg font-semibold text-slate-900">MedicalRAG</h1>
            <p className="mt-0.5 text-sm text-slate-500">心血管专科医学知识问答</p>
          </div>
          <h2 className="text-xl font-semibold tracking-tight text-slate-900">
            {mode === 'login' ? '登录' : '创建账号'}
          </h2>
          <p className="mt-1 mb-6 text-sm text-slate-500">
            {mode === 'login' ? '继续使用你的问答历史' : '注册后即可开始提问'}
          </p>
          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <FieldLabel>用户名</FieldLabel>
              <Input
                placeholder="至少 2 个字符"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                minLength={2}
                autoComplete="username"
                required
              />
            </div>
            <div>
              <FieldLabel>密码</FieldLabel>
              <Input
                type="password"
                placeholder="至少 6 个字符"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                minLength={6}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                required
              />
            </div>
            {error && (
              <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {error}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? '请稍候…' : mode === 'login' ? '登录' : '注册并登录'}
            </Button>
          </form>
          <p className="mt-6 text-center text-sm text-slate-500">
            {mode === 'login' ? '还没有账号？' : '已有账号？'}
            <button
              className="ml-1 font-medium text-primary-700 hover:underline"
              onClick={() => {
                setMode(mode === 'login' ? 'register' : 'login')
                setError('')
              }}
            >
              {mode === 'login' ? '注册' : '去登录'}
            </button>
          </p>
        </div>
      </main>
    </div>
  )
}
