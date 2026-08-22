import { ArrowClockwise, Brain, CheckCircle, Copy, Keyhole, Waveform, WarningCircle } from '@phosphor-icons/react'
import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'

import { apiRequest } from '../../shared/api'
import { useAuth } from '../AuthContext'

interface ModelStatus {
  agent_connected: boolean
  asr: { name: string; configured: boolean }
  llm: { name: string; configured: boolean }
  storage: string
}

export function ModelsPage() {
  const { session } = useAuth()
  const [status, setStatus] = useState<ModelStatus | null>(null)
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    if (!session) return
    setLoading(true)
    try {
      setStatus(await apiRequest<ModelStatus>('/model-status', {}, session.token))
    } finally {
      setLoading(false)
    }
  }, [session])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const command = 'anti-bagu-agent configure-models'

  return (
    <section className="content-page">
      <div className="page-title-actions">
        <div>
          <span className="eyebrow">模型设置</span>
          <h1>模型 Key 由桌面 Agent 管理</h1>
          <p className="page-lead">网页不接收、不显示也不保存模型 Key。密钥只保存在当前 Mac 的系统钥匙串中。</p>
        </div>
        <button className="secondary-action compact-action" type="button" onClick={() => void refresh()} disabled={loading}><ArrowClockwise className={loading ? 'spin' : ''} size={18} />刷新状态</button>
      </div>

      <div className="key-privacy-banner">
        <Keyhole size={28} weight="duotone" />
        <div><strong>平台数据库不会持久化你的模型密钥</strong><span>任务预检时，Agent 通过加密连接把 Key 临时交给任务 Worker；任务结束后从内存清除。</span></div>
        <em>{status?.storage ?? 'macOS Keychain'}</em>
      </div>

      <div className="model-settings-grid">
        <ModelStatusCard kind="ASR 模型" name={status?.asr.name ?? 'Qwen Audio ASR Flash'} configured={status?.asr.configured ?? false} icon={<Waveform size={24} weight="duotone" />} />
        <ModelStatusCard kind="LLM 模型" name={status?.llm.name ?? 'DeepSeek V4 Flash Vision'} configured={status?.llm.configured ?? false} icon={<Brain size={24} weight="duotone" />} />
      </div>

      <div className="model-cli-guide">
        <div><span className="side-panel-label">桌面 CLI</span><h2>{status?.agent_connected ? '更新本地模型配置' : '先连接桌面 Agent'}</h2><p>在电脑终端运行命令，按提示分别粘贴 DashScope 和 DeepSeek Key。</p></div>
        <code>{command}</code>
        <button className="secondary-action compact-action" type="button" onClick={() => navigator.clipboard.writeText(command)}><Copy size={17} />复制命令</button>
      </div>
    </section>
  )
}

function ModelStatusCard({
  kind,
  name,
  configured,
  icon,
}: {
  kind: string
  name: string
  configured: boolean
  icon: ReactNode
}) {
  return (
    <section className="model-settings-block model-status-card">
      <header>
        <span className="model-icon">{icon}</span>
        <div><span className="model-kind">{kind}</span><h2>{name}</h2></div>
        <span className={`connected-pill ${configured ? '' : 'connected-pill--offline'}`}><i />{configured ? '已配置' : '未配置'}</span>
      </header>
      <div className={`model-connection-state ${configured ? '' : 'model-connection-state--missing'}`}>
        {configured ? <CheckCircle size={24} weight="fill" /> : <WarningCircle size={24} weight="duotone" />}
        <span><strong>{configured ? 'Key 已存入本地钥匙串' : '等待本地配置'}</strong><small>{configured ? '下次任务预检会验证实际连通性与延迟' : '完成 CLI 配置后回到这里刷新状态'}</small></span>
      </div>
    </section>
  )
}
