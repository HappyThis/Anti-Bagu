import { ArrowClockwise, CheckCircle, Database, DownloadSimple, HardDrives, Pulse, WarningCircle } from '@phosphor-icons/react'
import { useCallback, useEffect, useState } from 'react'

import { apiRequest } from '../../shared/api'
import { useAuth } from '../AuthContext'

interface SystemStatus {
  status: string
  load_average: number[]
  agent_connections: number
  active_runtimes: number
  audit_dropped_events: number
  database: string
  storage_dir: string
}

interface AuditRecord {
  timestamp: string
  level: string
  event: string
  session_id: string
  payload: Record<string, unknown>
}

export function AdminSystemPage() {
  const { session } = useAuth()
  const [system, setSystem] = useState<SystemStatus | null>(null)
  const [logs, setLogs] = useState<AuditRecord[]>([])
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    if (!session) return
    setLoading(true)
    try {
      const [status, logResult] = await Promise.all([
        apiRequest<SystemStatus>('/admin/system', {}, session.token),
        apiRequest<{ events: AuditRecord[] }>('/admin/logs?limit=60', {}, session.token),
      ])
      setSystem(status)
      setLogs(logResult.events)
    } finally {
      setLoading(false)
    }
  }, [session])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const logText = logs.map((log) => `${new Date(log.timestamp).toLocaleTimeString('zh-CN', { hour12: false })} ${log.level.padEnd(5)} ${log.event.padEnd(26)} session=${log.session_id.slice(0, 8)}`).join('\n')

  return (
    <section className="admin-page">
      <div className="page-title-actions admin-page-heading"><div><span className="eyebrow">平台诊断</span><h1>系统状态</h1><p className="page-lead">服务依赖、连接容量和最近结构化日志。</p></div><button className="secondary-action compact-action" type="button" onClick={() => void refresh()} disabled={loading}><ArrowClockwise className={loading ? 'spin' : ''} size={18} />立即检查</button></div>
      <div className="system-metrics"><span><small>服务状态</small><strong>{system?.status === 'ok' ? '正常' : '—'}</strong></span><span><small>Agent 连接</small><strong>{system?.agent_connections ?? '—'}</strong></span><span><small>活动运行时</small><strong>{system?.active_runtimes ?? '—'}</strong></span><span><small>丢弃日志</small><strong className={system?.audit_dropped_events ? 'metric-warning' : ''}>{system?.audit_dropped_events ?? '—'}</strong></span></div>
      <div className="system-health-list">
        <div><Pulse size={24} /><span><strong>Realtime Gateway</strong><small>Agent 会话 {system?.agent_connections ?? 0}</small></span><em><CheckCircle size={18} weight="fill" />正常</em></div>
        <div><HardDrives size={24} /><span><strong>Task Runtime</strong><small>活动实例 {system?.active_runtimes ?? 0} · load {system?.load_average?.[0]?.toFixed(2) ?? '—'}</small></span><em><CheckCircle size={18} weight="fill" />正常</em></div>
        <div><Database size={24} /><span><strong>PostgreSQL</strong><small>{system?.database ?? '正在检查'}</small></span><em><CheckCircle size={18} weight="fill" />正常</em></div>
        <div><WarningCircle size={24} /><span><strong>本地任务存储</strong><small>{system?.storage_dir ?? '正在检查'}</small></span><em className={system?.audit_dropped_events ? 'health-warning' : ''}>{system?.audit_dropped_events ? '存在丢弃' : '正常'}</em></div>
      </div>
      <section className="log-viewer">
        <header><div><h2>最近系统日志</h2><span>{logs.length} 条 · Key 与正文默认脱敏</span></div><div className="toolbar-actions"><select aria-label="日志级别"><option>全部级别</option><option>WARN</option><option>ERROR</option></select><button className="secondary-action compact-action" type="button" onClick={() => downloadLogs(logText)}><DownloadSimple size={18} />下载日志</button></div></header>
        <pre>{logText || '暂无系统日志'}</pre>
      </section>
    </section>
  )
}

function downloadLogs(content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'text/plain' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `anti-bagu-${new Date().toISOString().slice(0, 10)}.log`
  anchor.click()
  URL.revokeObjectURL(url)
}
