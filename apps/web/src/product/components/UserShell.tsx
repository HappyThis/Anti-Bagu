import {
  CaretDown,
  Desktop,
  GearSix,
  Plus,
  Question,
  Sparkle,
  Timer,
} from '@phosphor-icons/react'
import { NavLink, Outlet, useNavigate, useParams } from 'react-router-dom'

import { useProduct } from '../ProductContext'
import { useAuth } from '../AuthContext'
import type { TaskStatus } from '../types'

const STATUS_LABEL: Record<TaskStatus, string> = {
  draft: '待检查',
  checking: '检查中',
  check_failed: '检查失败',
  ready: '准备中',
  running: '进行中',
  paused: '已暂停',
  completed: '已完成',
}

export function UserShell() {
  const { tasks, loading, error } = useProduct()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { taskId } = useParams()

  return (
    <div className="product-app">
      <header className="product-topbar">
        <button className="brand-button" type="button" onClick={() => navigate('/tasks')}>
          Anti-Bagu
        </button>
        <span className="product-edition"><Sparkle size={14} weight="fill" />内测工作台</span>
        <span className="cloud-state"><span />云端服务正常</span>
        <div className="account-area">
          <button className="icon-button" type="button" aria-label="帮助">
            <Question size={20} />
          </button>
          <button className="account-button" type="button" onClick={() => void logout()} title="退出登录">
            <span className="avatar">{user?.username.slice(0, 1).toUpperCase()}</span>
            <span>{user?.username}</span>
            <CaretDown size={15} />
          </button>
        </div>
      </header>

      <div className="product-body">
        <aside className="task-sidebar">
          <div className="sidebar-heading-row">
            <div>
              <span>任务空间</span>
              <h2>所有任务</h2>
            </div>
            <b>{tasks.length}</b>
          </div>
          <button className="new-task-button" type="button" onClick={() => navigate('/tasks/new')}>
            <Plus size={18} weight="bold" />
            新建任务
          </button>

          <div className="task-list" aria-label="历史任务">
            {loading ? <span className="sidebar-message">正在加载任务…</span> : null}
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
            <NavLink to="/reviews"><Timer size={21} />复盘</NavLink>
            <NavLink to="/devices"><Desktop size={21} />设备</NavLink>
            <NavLink to="/models"><GearSix size={21} />模型设置</NavLink>
          </nav>
        </aside>

        <main className="product-main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
