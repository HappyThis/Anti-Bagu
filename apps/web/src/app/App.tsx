import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'

import { ActivationKeysPage } from '../product/admin/ActivationKeysPage'
import { AdminOverviewPage } from '../product/admin/AdminOverviewPage'
import { AdminSystemPage } from '../product/admin/AdminSystemPage'
import { AdminTasksPage } from '../product/admin/AdminTasksPage'
import { AdminUsersPage } from '../product/admin/AdminUsersPage'
import { AdminShell } from '../product/components/AdminShell'
import { UserShell } from '../product/components/UserShell'
import { AuthProvider, useAuth } from '../product/AuthContext'
import { ProductProvider, useProduct } from '../product/ProductContext'
import { CreateTaskPage } from '../product/pages/CreateTaskPage'
import { DevicesPage } from '../product/pages/DevicesPage'
import { LiveTaskPage } from '../product/pages/LiveTaskPage'
import { LoginPage } from '../product/pages/LoginPage'
import { MobileCompanionPage } from '../product/pages/MobileCompanionPage'
import { RegisterPage } from '../product/pages/RegisterPage'
import { ReviewDetailPage } from '../product/pages/ReviewDetailPage'
import { ReviewsPage } from '../product/pages/ReviewsPage'
import { TaskWorkspacePage } from '../product/pages/TaskWorkspacePage'
import { AgentAuthorizePage } from '../product/pages/AgentAuthorizePage'

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/m/pair/:pairingToken" element={<MobileCompanionPage />} />
          <Route path="/agent/authorize" element={<AgentAuthorizePage />} />

          <Route element={<RequireUser><ProductProvider><UserShell /></ProductProvider></RequireUser>}>
            <Route path="/tasks" element={<TaskIndexRedirect />} />
            <Route path="/tasks/new" element={<CreateTaskPage />} />
            <Route path="/tasks/:taskId" element={<TaskWorkspacePage />} />
            <Route path="/tasks/:taskId/live" element={<LiveTaskPage />} />
            <Route path="/reviews" element={<ReviewsPage />} />
            <Route path="/reviews/:reviewId" element={<ReviewDetailPage />} />
            <Route path="/devices" element={<DevicesPage />} />
            <Route path="/models" element={<Navigate to="/devices" replace />} />
          </Route>

          <Route path="/admin" element={<RequireAdmin><AdminShell /></RequireAdmin>}>
            <Route index element={<AdminOverviewPage />} />
            <Route path="activation-keys" element={<ActivationKeysPage />} />
            <Route path="users" element={<AdminUsersPage />} />
            <Route path="tasks" element={<AdminTasksPage />} />
            <Route path="system" element={<AdminSystemPage />} />
          </Route>

          <Route path="/" element={<HomeRedirect />} />
          <Route path="*" element={<HomeRedirect />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

function RequireUser({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="route-loading">正在确认登录状态…</div>
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  if (user.role === 'admin') return <Navigate to="/admin" replace />
  return children
}

function RequireAdmin({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="route-loading">正在确认登录状态…</div>
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== 'admin') return <Navigate to="/tasks" replace />
  return children
}

function HomeRedirect() {
  const { user, loading } = useAuth()
  if (loading) return <div className="route-loading">正在确认登录状态…</div>
  if (!user) return <Navigate to="/login" replace />
  return <Navigate to={user.role === 'admin' ? '/admin' : '/tasks'} replace />
}

function TaskIndexRedirect() {
  const { tasks, loading } = useProduct()
  if (loading) return <div className="route-loading">正在加载任务…</div>
  if (tasks[0]) return <Navigate to={`/tasks/${tasks[0].id}`} replace />
  return <Navigate to="/tasks/new" replace />
}
