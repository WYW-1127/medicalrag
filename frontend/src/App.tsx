import type { ReactNode } from 'react'
import { HashRouter, Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { clearToken, getToken } from './api/client'
import ChatPage from './pages/ChatPage'
import KnowledgePage from './pages/KnowledgePage'
import LoginPage from './pages/LoginPage'

function RequireAuth({ children }: { children: ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return <>{children}</>
}

function TopBar() {
  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4">
      <div className="flex items-center gap-1">
        <NavLink
          to="/"
          className={({ isActive }) =>
            `rounded-md px-3 py-1.5 text-sm font-medium ${isActive ? 'bg-primary-50 text-primary-800' : 'text-slate-600 hover:bg-slate-100'}`
          }
        >
          对话
        </NavLink>
        <NavLink
          to="/kb"
          className={({ isActive }) =>
            `rounded-md px-3 py-1.5 text-sm font-medium ${isActive ? 'bg-primary-50 text-primary-800' : 'text-slate-600 hover:bg-slate-100'}`
          }
        >
          知识库
        </NavLink>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-sm font-semibold text-primary-800">⚕ MedicalRAG</span>
        <button
          className="text-sm text-slate-500 hover:text-slate-700"
          onClick={() => {
            clearToken()
            window.location.hash = '#/login'
          }}
        >
          退出
        </button>
      </div>
    </header>
  )
}

function DisclaimerBar() {
  const { pathname } = useLocation()
  if (pathname === '/login') return null
  return (
    <div className="shrink-0 bg-amber-50 px-4 py-1.5 text-center text-xs text-amber-800">
      ⚠️ 内容基于公开医学资料由 AI 生成，仅供参考，不能替代专业医疗建议、诊断或治疗。急症请拨打
      120。
    </div>
  )
}

export default function App() {
  return (
    <HashRouter>
      <div className="flex h-screen flex-col">
        <DisclaimerBar />
        <TopBar />
        <div className="min-h-0 flex-1">
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/"
              element={
                <RequireAuth>
                  <ChatPage />
                </RequireAuth>
              }
            />
            <Route
              path="/kb"
              element={
                <RequireAuth>
                  <KnowledgePage />
                </RequireAuth>
              }
            />
          </Routes>
        </div>
      </div>
    </HashRouter>
  )
}
