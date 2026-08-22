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
}

const STATUS_LABEL: Record<string, string> = {
  draft: '待检查',
  checking: '检查中',
  check_failed: '检查失败',
  ready: '已就绪',
  running: '运行中',
  paused: '已暂停',
  completed: '已完成',
}

export function AdminTasksPage() {
  const { session } = useAuth()
  const [query, setQuery] = useState('')
  const [tasks, setTasks] = useState<AdminTask[]>([])

  useEffect(() => {
    if (!session) return
    apiRequest<AdminTask[]>('/admin/tasks', {}, session.token).then(setTasks)
  }, [session])

  const visibleTasks = tasks.filter((task) => `${task.name} ${task.username}`.toLowerCase().includes(query.trim().toLowerCase()))
  const running = tasks.filter((task) => task.status === 'running').length
  const failed = tasks.filter((task) => task.status === 'check_failed').length

  return (
    <section className="admin-page">
      <span className="eyebrow">运行监控</span><h1>任务</h1><p className="page-lead">管理员只处理连接和系统异常，任务内容需要受控授权才能查看。</p>
      <div className="task-monitor-summary"><span><Pulse size={21} weight="duotone" /><b>{running}</b><small>运行中</small></span><span><WarningCircle size={21} weight="duotone" /><b>{failed}</b><small>需要处理</small></span><span><b>{tasks.length}</b><small>累计任务</small></span></div>
      <div className="table-toolbar"><div><strong>最近任务</strong><span>按更新时间排序</span></div><div className="toolbar-actions"><label className="search-field"><MagnifyingGlass size={18} /><input placeholder="搜索任务或用户" value={query} onChange={(event) => setQuery(event.target.value)} /></label><button className="secondary-action compact-action" type="button"><FunnelSimple size={18} />状态</button></div></div>
      <div className="data-table admin-tasks-table">
        <div className="table-head"><span>任务 ID</span><span>任务名称</span><span>用户</span><span>状态</span><span>更新时间</span><span>操作</span></div>
        {visibleTasks.map((task) => {
          const label = STATUS_LABEL[task.status] ?? task.status
          return (
            <div className="table-row" key={task.id}>
              <code>{task.id.slice(0, 8)}</code><strong>{task.name}</strong><span>{task.username}</span>
              <span className={task.status === 'check_failed' ? 'task-alert' : ''}>{task.status === 'check_failed' ? <WarningCircle size={17} /> : null}{label}</span>
              <time>{new Date(task.updated_at).toLocaleString('zh-CN', { hour12: false })}</time><span><button className="table-action" type="button">诊断</button></span>
            </div>
          )
        })}
        {visibleTasks.length === 0 ? <div className="table-empty-state"><MagnifyingGlass size={24} /><strong>暂无匹配任务</strong><span>任务创建后会显示在这里</span></div> : null}
      </div>
      <div className="table-pagination"><span>显示 {visibleTasks.length} / {tasks.length} 条</span><div><button type="button" disabled>上一页</button><b>1</b><button type="button" disabled>下一页</button></div></div>
    </section>
  )
}
