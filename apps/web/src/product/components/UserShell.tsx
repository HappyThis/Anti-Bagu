import {
  CaretDown,
  GearSix,
  PlayCircle,
  SignOut,
  Timer,
} from '@phosphor-icons/react'
import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import { useAuth } from '../AuthContext'

export function UserShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [accountOpen, setAccountOpen] = useState(false)

  return (
    <div className="product-app">
      <div className="account-area floating-account">
        <button className="account-button" type="button" aria-label="账号菜单" onClick={() => setAccountOpen((current) => !current)} aria-expanded={accountOpen}>
          <span className="avatar">{user?.username.slice(0, 1).toUpperCase()}</span>
          <span>{user?.username}</span>
          <CaretDown size={15} />
        </button>
        {accountOpen ? <div className="account-menu"><span>当前账号</span><strong>{user?.username}</strong><button type="button" onClick={() => void logout()}><SignOut size={17} />退出登录</button></div> : null}
      </div>

      <div className="product-body">
        <aside className="task-sidebar">
          <button className="brand-button sidebar-brand" type="button" onClick={() => navigate('/tasks')}>
            Anti-Bagu
          </button>
          <nav className="user-nav" aria-label="用户功能">
            <NavLink to="/tasks"><PlayCircle size={21} />开始面试</NavLink>
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
