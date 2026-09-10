import type { FormEvent } from 'react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setToken } from '../api/client'
import { Button, Card, Input } from '../components/ui'

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
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-b from-primary-50 to-slate-100 p-4">
      <Card className="w-full max-w-sm p-8">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary-700 text-2xl text-white">
            ⚕
          </div>
          <h1 className="text-xl font-semibold text-slate-900">MedicalRAG</h1>
          <p className="mt-1 text-sm text-slate-500">医学知识检索与问答 Copilot</p>
        </div>
        <form onSubmit={onSubmit} className="space-y-4">
          <Input
            placeholder="用户名（≥2 字符）"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            minLength={2}
            required
          />
          <Input
            type="password"
            placeholder="密码（≥6 字符）"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={6}
            required
          />
          {error && <p className="text-sm text-rose-600">{error}</p>}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? '请稍候…' : mode === 'login' ? '登录' : '注册并登录'}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-slate-500">
          {mode === 'login' ? '没有账号？' : '已有账号？'}
          <button
            className="ml-1 text-primary-700 hover:underline"
            onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
          >
            {mode === 'login' ? '注册' : '去登录'}
          </button>
        </p>
      </Card>
    </div>
  )
}
