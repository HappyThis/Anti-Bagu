import { FunnelSimple, MagnifyingGlass, Pulse, WarningCircle } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'

import { apiRequest } from '../../shared/api'
import { useAuth } from '../AuthContext'

interface AdminTask {
  id: string
  name: string
  username: string
  status: string
  updated_at: string
  created_at: string
  deleted_at: string | null
  deleted_by_id: string | null
}

interface AdminTaskRecord {
  task: { id: string; name: string; status: string; created_at: string; started_at: string | null; ended_at: string | null; deleted_at: string | null }
  events: Array<{ id: number; type: string; created_at: string; payload: Record<string, unknown> }>
}

const STATUS_LABEL: Record<string, string> = {
  draft: '待准备',
  checking: '正在准备',
  check_failed: '需要帮助',
  ready: '可以开始',
  running: '面试中',
  paused: '已暂停',
  completed: '已完成',
}

export function AdminTasksPage() {
  const { session } = useAuth()
  const [query, setQuery] = useState('')
  const [tasks, setTasks] = useState<AdminTask[]>([])
  const [record, setRecord] = useState<AdminTaskRecord | null>(null)
  const [recordLoading, setRecordLoading] = useState(false)

  useEffect(() => {
    if (!session) return
    apiRequest<AdminTask[]>('/admin/tasks', {}, session.token).then(setTasks)
  }, [session])

  const visibleTasks = tasks.filter((task) => `${task.name} ${task.username}`.toLowerCase().includes(query.trim().toLowerCase()))
  const running = tasks.filter((task) => task.status === 'running').length
  const failed = tasks.filter((task) => task.status === 'check_failed').length
  const deleted = tasks.filter((task) => task.deleted_at).length

  async function restoreTask(taskId: string) {
    if (!session) return
    await apiRequest(`/admin/tasks/${taskId}/restore`, { method: 'POST' }, session.token)
    setTasks((current) => current.map((task) => task.id === taskId ? { ...task, deleted_at: null, deleted_by_id: null } : task))
  }

  async function viewRecord(taskId: string) {
    if (!session) return
    setRecordLoading(true)
    try {
      setRecord(await apiRequest<AdminTaskRecord>(`/admin/tasks/${taskId}/record`, {}, session.token))
    } finally {
      setRecordLoading(false)
    }
  }

  return (
    <section className="admin-page">
      <span className="eyebrow">面试管理</span><h1>面试</h1><p className="page-lead">查看面试是否正常进行；默认不展示用户的对话和回答内容。</p>
      <div className="task-monitor-summary"><span><Pulse size={21} weight="duotone" /><b>{running}</b><small>正在面试</small></span><span><WarningCircle size={21} weight="duotone" /><b>{failed}</b><small>需要帮助</small></span><span><b>{deleted}</b><small>用户已删除</small></span></div>
      <div className="table-toolbar"><div><strong>最近面试</strong><span>按更新时间排序</span></div><div className="toolbar-actions"><label className="search-field"><MagnifyingGlass size={18} /><input placeholder="搜索面试或用户" value={query} onChange={(event) => setQuery(event.target.value)} /></label><button className="secondary-action compact-action" type="button"><FunnelSimple size={18} />状态</button></div></div>
      <div className="data-table admin-tasks-table">
        <div className="table-head"><span>编号</span><span>面试名称</span><span>用户</span><span>状态</span><span>更新时间</span><span>操作</span></div>
        {visibleTasks.map((task) => {
          const label = task.deleted_at ? '用户已删除' : STATUS_LABEL[task.status] ?? task.status
          return (
            <div className="table-row" key={task.id}>
              <code>{task.id.slice(0, 8)}</code><strong>{task.name}</strong><span>{task.username}</span>
              <span className={task.deleted_at || task.status === 'check_failed' ? 'task-alert' : ''}>{task.status === 'check_failed' ? <WarningCircle size={17} /> : null}{label}</span>
              <time>{new Date(task.updated_at).toLocaleString('zh-CN', { hour12: false })}</time><span className="admin-task-actions"><button className="table-action" type="button" onClick={() => void viewRecord(task.id)}>{recordLoading ? '加载中' : '查看记录'}</button>{task.deleted_at ? <button className="table-action" type="button" onClick={() => void restoreTask(task.id)}>恢复</button> : null}</span>
            </div>
          )
        })}
        {visibleTasks.length === 0 ? <div className="table-empty-state"><MagnifyingGlass size={24} /><strong>暂无匹配面试</strong><span>用户创建面试后会显示在这里</span></div> : null}
      </div>
      <div className="table-pagination"><span>显示 {visibleTasks.length} / {tasks.length} 条</span><div><button type="button" disabled>上一页</button><b>1</b><button type="button" disabled>下一页</button></div></div>
      {record ? <div className="dialog-backdrop" role="presentation"><section className="admin-record-dialog" role="dialog" aria-modal="true" aria-labelledby="admin-record-title"><div className="page-title-actions"><div><span className="eyebrow">完整记录</span><h2 id="admin-record-title">{record.task.name}</h2><p>{record.events.length} 条系统事件 · {record.task.deleted_at ? '用户已删除' : STATUS_LABEL[record.task.status] ?? record.task.status}</p></div><button className="secondary-action compact-action" type="button" onClick={() => setRecord(null)}>关闭</button></div><div className="admin-record-events">{record.events.map((event) => <article key={event.id}><time>{new Date(event.created_at).toLocaleTimeString('zh-CN', { hour12: false })}</time><strong>{event.type}</strong><pre>{JSON.stringify(event.payload, null, 2)}</pre></article>)}</div></section></div> : null}
    </section>
  )
}
