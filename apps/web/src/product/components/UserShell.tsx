import {
  CaretDown,
  GearSix,
  House,
  Plus,
  Question,
  SignOut,
  Sparkle,
  Timer,
} from '@phosphor-icons/react'
import { useState } from 'react'
import { NavLink, Outlet, useNavigate, useParams } from 'react-router-dom'

import { useProduct } from '../ProductContext'
import { useAuth } from '../AuthContext'
import type { TaskStatus } from '../types'

const STATUS_LABEL: Record<TaskStatus, string> = {
  draft: '待准备',
  checking: '正在准备',
  check_failed: '需要准备',
  ready: '可以开始',
  running: '面试中',
  paused: '已暂停',
  completed: '已完成',
}

export function UserShell() {
  const { tasks, loading, error } = useProduct()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { taskId } = useParams()
  const [accountOpen, setAccountOpen] = useState(false)

  return (
    <div className="product-app">
      <header className="product-topbar">
        <button className="brand-button" type="button" onClick={() => navigate('/tasks')}>
          Anti-Bagu
        </button>
        <span className="product-edition"><Sparkle size={14} weight="fill" />准备面试</span>
        <span className="cloud-state"><span />已连接</span>
        <div className="account-area">
          <button className="icon-button" type="button" aria-label="帮助">
            <Question size={20} />
          </button>
          <button className="account-button" type="button" onClick={() => setAccountOpen((current) => !current)} aria-expanded={accountOpen}>
            <span className="avatar">{user?.username.slice(0, 1).toUpperCase()}</span>
            <span>{user?.username}</span>
            <CaretDown size={15} />
          </button>
          {accountOpen ? <div className="account-menu"><span>当前账号</span><strong>{user?.username}</strong><button type="button" onClick={() => void logout()}><SignOut size={17} />退出登录</button></div> : null}
        </div>
      </header>

      <div className="product-body">
        <aside className="task-sidebar">
          <div className="sidebar-heading-row">
            <div>
              <span>面试记录</span>
              <h2>所有面试</h2>
            </div>
            <b>{tasks.length}</b>
          </div>
          <button className="new-task-button" type="button" onClick={() => navigate('/tasks/new')}>
            <Plus size={18} weight="bold" />
            新建面试
          </button>

          <div className="task-list" aria-label="历史面试">
            {loading ? <span className="sidebar-message">正在加载面试…</span> : null}
            {error ? <span className="sidebar-message sidebar-message--error">{error}</span> : null}
            {tasks.map((task) => (
              <button
                className={`task-list-item ${task.id === taskId ? 'task-list-item--selected' : ''}`}
                key={task.id}
                type="button"
                onClick={() => navigate(`/tasks/${task.id}`)}
              >
                <strong>{task.name}</strong>
                <span>
                  <time>{task.createdAt}</time>
                  <em className={`task-state task-state--${task.status}`}>{STATUS_LABEL[task.status]}</em>
                </span>
              </button>
            ))}
          </div>

          <nav className="user-nav" aria-label="用户功能">
            <NavLink to="/tasks"><House size={21} />准备面试</NavLink>
            <NavLink to="/reviews"><Timer size={21} />面试记录</NavLink>
            <NavLink to="/devices"><GearSix size={21} />设置</NavLink>
          </nav>
        </aside>

        <main className="product-main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
