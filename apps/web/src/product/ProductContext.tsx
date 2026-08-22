import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { apiRequest } from '../shared/api'
import { useAuth } from './AuthContext'
import type {
  InterviewTask,
  PairingInfo,
  PreflightCheck,
  TaskStatus,
} from './types'

interface ApiTask {
  id: string
  name: string
  mode: 'interview' | 'practice'
  mobile_required: boolean
  status: TaskStatus
  created_at: string
}

interface ApiPreflight {
  task: ApiTask
  checks: Array<{
    key: string
    label: string
    ok: boolean
    detail: string
    latency_ms: number | null
  }>
  ready: boolean
}

interface ProductContextValue {
  tasks: InterviewTask[]
  loading: boolean
  error: string
  refreshTasks: () => Promise<void>
  createTask: (name: string, mode: InterviewTask['mode'], mobileRequired: boolean) => Promise<string>
  renameTask: (taskId: string, name: string) => Promise<void>
  updateTaskStatus: (taskId: string, status: TaskStatus) => Promise<void>
  preflightTask: (taskId: string) => Promise<{ ready: boolean; checks: PreflightCheck[] }>
  getPreflight: (taskId: string) => Promise<{ ready: boolean; checks: PreflightCheck[] }>
  getPairing: (taskId: string) => Promise<PairingInfo>
  getTask: (taskId: string | undefined) => InterviewTask | undefined
}

const ProductContext = createContext<ProductContextValue | null>(null)

function mapTask(task: ApiTask): InterviewTask {
  return {
    id: task.id,
    name: task.name,
    createdAt: new Date(task.created_at).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).replaceAll('/', '-'),
    status: task.status,
    mode: task.mode,
    mobileRequired: task.mobile_required,
  }
}

export function ProductProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth()
  const [tasks, setTasks] = useState<InterviewTask[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refreshTasks = useCallback(async () => {
    if (!session) return
    setLoading(true)
    try {
      const rows = await apiRequest<ApiTask[]>('/tasks', {}, session.token)
      setTasks(rows.map(mapTask))
      setError('')
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '任务加载失败')
    } finally {
      setLoading(false)
    }
  }, [session])

  useEffect(() => {
    void refreshTasks()
  }, [refreshTasks])

  const value = useMemo<ProductContextValue>(() => ({
    tasks,
    loading,
    error,
    refreshTasks,
    async createTask(name, mode, mobileRequired) {
      const task = await apiRequest<ApiTask>('/tasks', {
        method: 'POST',
        body: JSON.stringify({ name, mode, mobile_required: mobileRequired }),
      }, session?.token)
      setTasks((current) => [mapTask(task), ...current])
      return task.id
    },
    async renameTask(taskId, name) {
      const task = await apiRequest<ApiTask>(`/tasks/${taskId}`, {
        method: 'PATCH',
        body: JSON.stringify({ name }),
      }, session?.token)
      setTasks((current) => current.map((item) => item.id === taskId ? mapTask(task) : item))
    },
    async updateTaskStatus(taskId, status) {
      const currentStatus = tasks.find((task) => task.id === taskId)?.status
      const endpoint = status === 'running'
        ? (currentStatus === 'paused' ? 'resume' : 'start')
        : status === 'paused' ? 'pause' : status === 'completed' ? 'end' : null
      if (!endpoint) return
      const task = await apiRequest<ApiTask>(`/tasks/${taskId}/${endpoint}`, { method: 'POST' }, session?.token)
      setTasks((current) => current.map((item) => item.id === taskId ? mapTask(task) : item))
    },
    async preflightTask(taskId) {
      const response = await apiRequest<ApiPreflight>(`/tasks/${taskId}/preflight`, { method: 'POST' }, session?.token)
      setTasks((current) => current.map((item) => item.id === taskId ? mapTask(response.task) : item))
      return {
        ready: response.ready,
        checks: mapChecks(response.checks),
      }
    },
    async getPreflight(taskId) {
      const response = await apiRequest<Pick<ApiPreflight, 'ready' | 'checks'>>(`/tasks/${taskId}/preflight`, {}, session?.token)
      return { ready: response.ready, checks: mapChecks(response.checks) }
    },
    async getPairing(taskId) {
      const response = await apiRequest<{
        token: string
        url: string
        expires_at: number
        connected: boolean
      }>(`/tasks/${taskId}/pairing`, { method: 'POST' }, session?.token)
      return {
        token: response.token,
        url: response.url,
        expiresAt: response.expires_at,
        connected: response.connected,
      }
    },
    getTask(taskId) {
      return tasks.find((task) => task.id === taskId)
    },
  }), [error, loading, refreshTasks, session?.token, tasks])

  return <ProductContext.Provider value={value}>{children}</ProductContext.Provider>
}

function mapChecks(checks: ApiPreflight['checks']): PreflightCheck[] {
  return checks.map((check) => ({
    key: check.key,
    label: check.label,
    ok: check.ok,
    detail: check.detail,
    latencyMs: check.latency_ms,
  }))
}

export function useProduct() {
  const context = useContext(ProductContext)
  if (!context) throw new Error('useProduct must be used inside ProductProvider')
  return context
}
