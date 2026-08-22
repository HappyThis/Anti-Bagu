import { CheckCircle, Desktop, LockKey, XCircle } from '@phosphor-icons/react'
import { useState, type ReactNode } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { apiRequest } from '../../shared/api'
import { useAuth } from '../AuthContext'

type AuthorizationState = 'ready' | 'submitting' | 'approved' | 'cancelled' | 'error'

export function AgentAuthorizePage() {
  const { user, loading } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [state, setState] = useState<AuthorizationState>('ready')
  const [message, setMessage] = useState('')
  const code = new URLSearchParams(location.search).get('code')?.trim() ?? ''

  if (loading) return <div className="route-loading">正在确认登录状态…</div>
  if (!user) {
    return (
      <Navigate
        to="/login"
        state={{ from: `${location.pathname}${location.search}` }}
        replace
      />
    )
  }

  async function approve() {
    if (!code) return
    setState('submitting')
    setMessage('')
    try {
      await apiRequest(`/agent/authorizations/code/${encodeURIComponent(code)}/approve`, {
        method: 'POST',
      })
      setState('approved')
    } catch (requestError) {
      setState('error')
      setMessage(requestError instanceof Error ? requestError.message : '登录请求已失效，请返回电脑助手重试。')
    }
  }

  async function cancel() {
    if (!code) {
      setState('cancelled')
      return
    }
    setState('submitting')
    try {
      await apiRequest(`/agent/authorizations/code/${encodeURIComponent(code)}/cancel`, {
        method: 'POST',
      })
      setState('cancelled')
    } catch (requestError) {
      setState('error')
      setMessage(requestError instanceof Error ? requestError.message : '无法取消，请直接关闭页面。')
    }
  }

  if (state === 'approved') {
    return (
      <AuthorizationResult
        icon={<CheckCircle size={38} weight="fill" />}
        tone="success"
        title="电脑助手已登录"
        description="可以关闭这个页面，返回电脑助手继续准备。"
      />
    )
  }

  if (state === 'cancelled') {
    return (
      <AuthorizationResult
        icon={<XCircle size={38} weight="fill" />}
        tone="muted"
        title="已取消登录"
        description="电脑助手没有获得你的登录信息，可以直接关闭这个页面。"
      />
    )
  }

  return (
    <main className="agent-auth-page">
      <a className="agent-auth-brand" href="/">Anti-Bagu</a>
      <section className="agent-auth-card">
        <span className="agent-auth-icon"><Desktop size={30} weight="duotone" /></span>
        <span className="agent-auth-eyebrow">电脑助手登录</span>
        <h1>允许这台电脑登录？</h1>
        <p>电脑助手将使用账号 <strong>@{user.username}</strong> 连接 Anti-Bagu。</p>
        <div className="agent-auth-safety">
          <LockKey size={19} weight="duotone" />
          <span>电脑助手无法读取你的网页密码，你也无需在电脑助手里再次输入密码。</span>
        </div>
        {!code ? <div className="form-error" role="alert">登录链接不完整，请返回电脑助手重新打开。</div> : null}
        {state === 'error' ? <div className="form-error" role="alert">{message}</div> : null}
        <div className="agent-auth-actions">
          <button
            className="primary-action"
            type="button"
            disabled={!code || state === 'submitting'}
            onClick={approve}
          >
            {state === 'submitting' ? '正在登录…' : '允许登录'}
          </button>
          <button className="secondary-action" type="button" disabled={state === 'submitting'} onClick={cancel}>
            取消
          </button>
        </div>
        <button
          className="agent-auth-switch"
          type="button"
          onClick={() => navigate('/login', { state: { from: `${location.pathname}${location.search}` } })}
        >
          不是 @{user.username}？切换账号
        </button>
      </section>
      <small>只有刚刚打开登录页面的电脑助手能够取得这次登录结果。</small>
    </main>
  )
}

function AuthorizationResult({
  icon,
  tone,
  title,
  description,
}: {
  icon: ReactNode
  tone: 'success' | 'muted'
  title: string
  description: string
}) {
  return (
    <main className="agent-auth-page">
      <a className="agent-auth-brand" href="/">Anti-Bagu</a>
      <section className={`agent-auth-card agent-auth-result agent-auth-result--${tone}`}>
        <span className="agent-auth-result-icon">{icon}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </section>
    </main>
  )
}
