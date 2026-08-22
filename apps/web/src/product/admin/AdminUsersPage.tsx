import { DownloadSimple, FunnelSimple, MagnifyingGlass, UserCircle } from '@phosphor-icons/react'
import { useCallback, useEffect, useState } from 'react'

import { apiRequest } from '../../shared/api'
import { useAuth } from '../AuthContext'

interface AdminUser {
  id: string
  username: string
  display_name: string
  role: string
  status: 'active' | 'disabled'
  created_at: string
  task_count: number
}

export function AdminUsersPage() {
  const { session } = useAuth()
  const [query, setQuery] = useState('')
  const [users, setUsers] = useState<AdminUser[]>([])

  const refresh = useCallback(async () => {
    if (!session) return
    setUsers(await apiRequest<AdminUser[]>('/admin/users', {}, session.token))
  }, [session])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const visibleUsers = users.filter((user) => `${user.display_name} ${user.username}`.toLowerCase().includes(query.trim().toLowerCase()))

  async function toggleStatus(user: AdminUser) {
    if (!session || user.role === 'admin') return
    const next = user.status === 'active' ? 'disabled' : 'active'
    await apiRequest(`/admin/users/${user.id}?status=${next}`, { method: 'PATCH' }, session.token)
    await refresh()
  }

  return (
    <section className="admin-page">
      <div className="page-title-actions admin-page-heading"><div><span className="eyebrow">账号管理</span><h1>用户</h1><p className="page-lead">用户使用激活密钥、用户名和密码注册；平台不收集邮箱或手机号。</p></div><button className="secondary-action compact-action" type="button"><DownloadSimple size={18} />导出列表</button></div>
      <div className="table-toolbar"><div><strong>{users.length} 位用户</strong><span>{users.filter((user) => user.status === 'active').length} 位正常</span></div><div className="toolbar-actions"><label className="search-field"><MagnifyingGlass size={18} /><input placeholder="搜索用户名" value={query} onChange={(event) => setQuery(event.target.value)} /></label><button className="secondary-action compact-action" type="button"><FunnelSimple size={18} />状态</button></div></div>
      <div className="data-table users-table">
        <div className="table-head"><span>用户</span><span>注册时间</span><span>任务</span><span>状态</span><span>操作</span></div>
        {visibleUsers.map((user) => {
          const label = user.status === 'active' ? '正常' : '已停用'
          return (
            <div className="table-row" key={user.id}>
              <span className="user-cell"><UserCircle size={25} /><span><strong>{user.display_name || user.username}</strong><small>@{user.username}{user.role === 'admin' ? ' · 管理员' : ''}</small></span></span>
              <time>{new Date(user.created_at).toLocaleDateString('zh-CN')}</time><span>{user.task_count} 个</span><span><em className={`status-badge status-badge--${label}`}>{label}</em></span>
              <span><button className="table-action" type="button" disabled={user.role === 'admin'} onClick={() => void toggleStatus(user)}>{user.status === 'active' ? '停用' : '恢复'}</button></span>
            </div>
          )
        })}
        {visibleUsers.length === 0 ? <div className="table-empty-state"><MagnifyingGlass size={24} /><strong>没有匹配的用户</strong><span>换一个用户名试试</span></div> : null}
      </div>
      <div className="table-pagination"><span>显示 {visibleUsers.length} / {users.length} 条</span><div><button type="button" disabled>上一页</button><b>1</b><button type="button" disabled>下一页</button></div></div>
    </section>
  )
}
