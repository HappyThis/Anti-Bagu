export type TaskStatus = 'draft' | 'checking' | 'check_failed' | 'ready' | 'running' | 'paused' | 'completed'

export interface InterviewTask {
  id: string
  name: string
  createdAt: string
  status: TaskStatus
  mode: 'interview' | 'practice'
  mobileRequired: boolean
  deletedAt: string | null
}

export interface PreflightCheck {
  key: string
  label: string
  ok: boolean
  detail: string
  latencyMs: number | null
}

export interface PairingInfo {
  token: string
  url: string
  expiresAt: number
  connected: boolean
}

export interface ReviewRecord {
  id: string
  taskId: string
  taskName: string
  date: string
  duration: string
  questionCount: number
  avgLatency: number
}

export interface ActivationKeyRecord {
  id: string
  displayKey: string
  status: '未使用' | '已使用' | '已吊销'
  createdAt: string
  expiresAt: string
  boundUser?: string
}

export interface AdminUserRecord {
  id: string
  name: string
  username: string
  registeredAt: string
  taskCount: number
  status: '正常' | '已停用'
}
