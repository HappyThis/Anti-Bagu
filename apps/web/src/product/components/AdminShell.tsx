import {
  CaretDown,
  CirclesFour,
  Heartbeat,
  Key,
  ListMagnifyingGlass,
  SignOut,
  SquaresFour,
  Users,
} from '@phosphor-icons/react'
import { NavLink, Outlet } from 'react-router-dom'

import { useAuth } from '../AuthContext'

export function AdminShell() {
  const { user, logout } = useAuth()
  return (
    <div className="admin-app">
      <header className="admin-topbar">
        <div className="admin-brand">
          <strong>Anti-Bagu</strong>
          <span>管理端</span>
        </div>
        <div className="admin-environment"><CirclesFour size={16} weight="fill" />生产环境 · 华北</div>
        <button className="account-button" type="button" onClick={() => void logout()} title="退出登录">
          <span className="avatar avatar--admin">A</span>
          <span>{user?.username}</span>
          <CaretDown size={15} />
        </button>
      </header>
      <div className="admin-body">
        <aside className="admin-sidebar">
          <span className="nav-section-label">平台管理</span>
          <nav aria-label="管理功能">
            <NavLink to="/admin" end><SquaresFour size={20} />概览</NavLink>
            <NavLink to="/admin/activation-keys"><Key size={20} />激活密钥</NavLink>
            <NavLink to="/admin/users"><Users size={20} />用户</NavLink>
            <NavLink to="/admin/tasks"><ListMagnifyingGlass size={20} />任务</NavLink>
            <NavLink to="/admin/system"><Heartbeat size={20} />系统状态</NavLink>
          </nav>
          <div className="admin-sidebar-footer">
            <span>Anti-Bagu Cloud</span>
            <small>v0.4.0 · 内测</small>
            <a className="admin-exit" href="/tasks">
              <SignOut size={20} />退出管理端
            </a>
          </div>
        </aside>
        <main className="admin-main"><Outlet /></main>
      </div>
    </div>
  )
}
