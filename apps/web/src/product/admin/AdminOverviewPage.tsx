import { ArrowClockwise, ArrowRight, Heartbeat, Key, Pulse, Users } from '@phosphor-icons/react'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { apiRequest } from '../../shared/api'
import { useAuth } from '../AuthContext'

interface Overview {
  users: number
  available_keys: number
  active_tasks: number
  today_tasks: number
  agent_connections: number
  active_runtimes: number
  recent_events: Array<{
    id: number
    action: string
    target_id: string | null
    created_at: string
  }>
}

export function AdminOverviewPage() {
  const { session } = useAuth()
  const navigate = useNavigate()
  const [overview, setOverview] = useState<Overview | null>(null)
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    if (!session) return
    setLoading(true)
    try {
      setOverview(await apiRequest<Overview>('/admin/overview', {}, session.token))
    } finally {
      setLoading(false)
    }
  }, [session])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return (
    <section className="admin-page">
      <div className="page-title-actions admin-page-heading">
        <div><span className="eyebrow">运营概览</span><h1>平台运行正常</h1><p className="page-lead">只展示运行与账号元数据，管理员默认不能查看用户的面试内容。</p></div>
        <button className="secondary-action compact-action" type="button" onClick={() => void refresh()} disabled={loading}><ArrowClockwise className={loading ? 'spin' : ''} size={18} />刷新数据</button>
      </div>

      <div className="admin-summary">
        <div><Users size={24} /><span>注册用户</span><strong>{overview?.users ?? '—'}</strong><small>全部有效账户</small></div>
        <div><Key size={24} /><span>可用激活密钥</span><strong>{overview?.available_keys ?? '—'}</strong><small>一次性注册凭证</small></div>
        <div><Pulse size={24} /><span>当前运行任务</span><strong>{overview?.active_tasks ?? '—'}</strong><small>今日累计 {overview?.today_tasks ?? '—'}</small></div>
        <div><Heartbeat size={24} /><span>Agent 连接</span><strong>{overview?.agent_connections ?? '—'}</strong><small>{overview?.active_runtimes ?? 0} 个任务运行时</small></div>
      </div>

      <div className="admin-grid">
        <section className="admin-panel">
          <header><h2>实时服务</h2><span className="connected-pill"><i />全部正常</span></header>
          <div className="health-row"><strong>Realtime Gateway</strong><span>{overview?.agent_connections ?? 0} 个 Agent</span><em>正常</em></div>
          <div className="health-row"><strong>Task Runtime</strong><span>{overview?.active_runtimes ?? 0} 个实例</span><em>正常</em></div>
          <div className="health-row"><strong>Task Event Store</strong><span>PostgreSQL + JSONL</span><em>正常</em></div>
          <div className="health-row"><strong>Local Artifact Storage</strong><span>按任务隔离</span><em>正常</em></div>
          <button className="panel-footer-action" type="button" onClick={() => navigate('/admin/system')}>查看系统状态<ArrowRight size={17} /></button>
        </section>
        <section className="admin-panel">
          <header><h2>最近事件</h2><span>最新 {overview?.recent_events.length ?? 0} 条</span></header>
          {(overview?.recent_events ?? []).slice(0, 4).map((event) => (
            <div className="event-row" key={event.id}><time>{new Date(event.created_at).toLocaleTimeString('zh-CN', { hour12: false })}</time><span>{actionLabel(event.action)}</span><em>{event.target_id?.slice(0, 8) ?? '—'}</em></div>
          ))}
          {!overview?.recent_events.length ? <div className="table-empty-state table-empty-state--compact"><span>暂无平台事件</span></div> : null}
          <button className="panel-footer-action" type="button">查看审计日志<ArrowRight size={17} /></button>
        </section>
      </div>
      <p className="admin-updated-at">实时读取控制面数据 · 点击刷新获取最新状态</p>
    </section>
  )
}

function actionLabel(action: string) {
  return ({
    'user.registered': '用户完成注册',
    'activation_key.created': '激活密钥已生成',
    'activation_key.revoked': '激活密钥已吊销',
    'task.created': '用户创建任务',
    'task.running': '任务开始运行',
    'task.completed': '任务已结束',
  } as Record<string, string>)[action] ?? action
}
