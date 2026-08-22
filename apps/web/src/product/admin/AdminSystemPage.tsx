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

  const logText = logs.map((log) => `${log.timestamp} ${log.level} ${log.event}`).join('\n')

  return (
    <section className="admin-page">
      <div className="page-title-actions admin-page-heading"><div><span className="eyebrow">运行情况</span><h1>服务状态</h1><p className="page-lead">查看电脑连接、面试处理和数据保存是否正常。</p></div><button className="secondary-action compact-action" type="button" onClick={() => void refresh()} disabled={loading}><ArrowClockwise className={loading ? 'spin' : ''} size={18} />重新确认</button></div>
      <div className="system-metrics"><span><small>整体状态</small><strong>{system?.status === 'ok' ? '正常' : '—'}</strong></span><span><small>在线电脑</small><strong>{system?.agent_connections ?? '—'}</strong></span><span><small>已打开面试</small><strong>{system?.active_runtimes ?? '—'}</strong></span><span><small>未保存记录</small><strong className={system?.audit_dropped_events ? 'metric-warning' : ''}>{system?.audit_dropped_events ?? '—'}</strong></span></div>
      <div className="system-health-list">
        <div><Pulse size={24} /><span><strong>电脑连接</strong><small>{system?.agent_connections ?? 0} 台电脑在线</small></span><em><CheckCircle size={18} weight="fill" />正常</em></div>
        <div><HardDrives size={24} /><span><strong>面试处理</strong><small>{system?.active_runtimes ?? 0} 场面试已打开</small></span><em><CheckCircle size={18} weight="fill" />正常</em></div>
        <div><Database size={24} /><span><strong>面试记录</strong><small>{system?.database === 'connected' ? '保存正常' : '正在确认'}</small></span><em><CheckCircle size={18} weight="fill" />正常</em></div>
        <div><WarningCircle size={24} /><span><strong>录音文件</strong><small>文件保存位置正常</small></span><em className={system?.audit_dropped_events ? 'health-warning' : ''}>{system?.audit_dropped_events ? '需要查看' : '正常'}</em></div>
      </div>
      <section className="log-viewer">
        <header><div><h2>最近运行记录</h2><span>{logs.length} 条</span></div><div className="toolbar-actions"><button className="secondary-action compact-action" type="button" onClick={() => downloadLogs(logText)}><DownloadSimple size={18} />导出记录</button></div></header>
        <div className="plain-log-list">{logs.slice(-12).reverse().map((log) => <div key={`${log.timestamp}-${log.event}`}><time>{new Date(log.timestamp).toLocaleTimeString('zh-CN', { hour12: false })}</time><span>{eventLabel(log.event)}</span><em className={log.level === 'WARNING' || log.level === 'ERROR' ? 'health-warning' : ''}>{log.level === 'WARNING' || log.level === 'ERROR' ? '需要查看' : '正常'}</em></div>)}{logs.length === 0 ? <p>暂无运行记录</p> : null}</div>
      </section>
    </section>
  )
}

function eventLabel(event: string) {
  return ({
    'server.started': '服务已启动',
    'server.stopped': '服务已停止',
    'ui.connected': '用户页面已连接',
    'ui.disconnected': '用户页面已断开',
    'audio.connected': '面试声音已连接',
    'audio.disconnected': '面试声音已断开',
    'focus.updated': '新的面试问题已整理',
    'answer.completed': '建议回答已生成',
    'task.status': '面试状态已更新',
  } as Record<string, string>)[event] ?? '服务状态已更新'
}

function downloadLogs(content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: 'text/plain' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `anti-bagu-${new Date().toISOString().slice(0, 10)}.log`
  anchor.click()
  URL.revokeObjectURL(url)
}
