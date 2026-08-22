import {
  ArrowClockwise,
  Brain,
  Broadcast,
  CellSignalFull,
  CheckCircle,
  LockKey,
  Microphone,
  PencilSimple,
  Play,
  ShieldCheck,
  SpeakerHigh,
  Waveform,
  WarningCircle,
} from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import QRCode from 'react-qr-code'
import { Navigate, useNavigate, useParams } from 'react-router-dom'

import { useProduct } from '../ProductContext'
import { StatusRow } from '../components/StatusRow'
import type { PreflightCheck } from '../types'

const CHECK_ICONS = {
  agent: Broadcast,
  agent_response: Broadcast,
  system_audio: SpeakerHigh,
  microphone: Microphone,
  asr: Waveform,
  llm: Brain,
  mobile: CellSignalFull,
} as const

export function TaskWorkspacePage() {
  const { taskId } = useParams()
  const navigate = useNavigate()
  const { getTask, loading, renameTask, updateTaskStatus, preflightTask, getPreflight, getPairing } = useProduct()
  const task = getTask(taskId)
  const [checking, setChecking] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [draftName, setDraftName] = useState(task?.name ?? '')
  const [checks, setChecks] = useState<PreflightCheck[]>([])
  const [pairingUrl, setPairingUrl] = useState('')
  const [phoneConnected, setPhoneConnected] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!taskId) return
    let disposed = false
    async function refreshPairing() {
      try {
        const pairing = await getPairing(taskId as string)
        if (!disposed) {
          setPairingUrl(pairing.url)
          setPhoneConnected(pairing.connected)
        }
      } catch {
        if (!disposed) setPairingUrl('')
      }
    }
    void refreshPairing()
    const timer = window.setInterval(refreshPairing, 3000)
    return () => {
      disposed = true
      window.clearInterval(timer)
    }
  }, [getPairing, taskId])

  useEffect(() => {
    if (!taskId) return
    getPreflight(taskId).then((result) => setChecks(result.checks)).catch(() => setChecks([]))
  }, [getPreflight, taskId])

  if (loading) return <div className="route-loading">正在加载任务…</div>
  if (!task) return <Navigate to="/tasks" replace />
  const activeTask = task

  async function recheck() {
    setChecking(true)
    setError('')
    try {
      const result = await preflightTask(activeTask.id)
      setChecks(result.checks)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '系统检查失败')
    } finally {
      setChecking(false)
    }
  }

  async function saveName() {
    const name = draftName.trim()
    if (name) await renameTask(activeTask.id, name)
    setRenaming(false)
  }

  async function startTask() {
    setError('')
    try {
      await updateTaskStatus(activeTask.id, 'running')
      navigate(`/tasks/${activeTask.id}/live`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '任务启动失败')
    }
  }

  const ready = activeTask.status === 'ready'
  const failed = activeTask.status === 'check_failed'

  return (
    <div className="task-workspace-page">
      <section className="task-readiness">
        <span className="eyebrow">当前任务</span>
        <div className="task-title-row">
          {renaming ? (
            <div className="rename-control">
              <input
                autoFocus
                value={draftName}
                onChange={(event) => setDraftName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') saveName()
                  if (event.key === 'Escape') setRenaming(false)
                }}
              />
              <button type="button" onClick={saveName}>保存</button>
            </div>
          ) : (
            <>
              <h1>{activeTask.name}</h1>
              <button
                className="rename-button"
                type="button"
                onClick={() => {
                  setDraftName(activeTask.name)
                  setRenaming(true)
                }}
              >
                <PencilSimple size={19} />编辑
              </button>
            </>
          )}
        </div>
        <div className="task-meta">
          <span>面试官模式</span>
          <i />
          <span>{activeTask.mode === 'practice' ? '模拟模式' : '云端模式'}</span>
        </div>

        <div className={`readiness-heading ${failed ? 'readiness-heading--failed' : !ready ? 'readiness-heading--pending' : ''}`}>
          {failed ? <WarningCircle size={52} weight="fill" /> : <CheckCircle size={52} weight="fill" />}
          <div>
            <h2>{checking ? '正在执行系统检查' : ready ? '系统检查通过' : failed ? '系统检查未通过' : '开始前需要完成检查'}</h2>
            <p>{checking ? '正在验证监听端、音频和模型连接…' : ready ? '所有系统均已就绪，可以开始面试' : failed ? '请根据下方结果修复后重新检查' : '将检查桌面 Agent、双路音频、模型和手机连接'}</p>
          </div>
        </div>

        <div className="status-list">
          {checks.length === 0 ? <div className="preflight-empty"><ShieldCheck size={24} weight="duotone" /><span><strong>尚未执行检查</strong><small>保持桌面 Agent 在线，然后点击“开始检查”。</small></span></div> : null}
          {checks.map((check) => (
            <StatusRow
              icon={CHECK_ICONS[check.key as keyof typeof CHECK_ICONS] ?? Broadcast}
              label={check.label}
              detail={check.detail}
              latency={check.latencyMs === null ? '—' : check.latencyMs >= 1000 ? `${(check.latencyMs / 1000).toFixed(2)} s` : `${Math.round(check.latencyMs)} ms`}
              ok={check.ok}
              checking={checking}
              key={check.key}
            />
          ))}
        </div>

        {error ? <div className="form-error preflight-error" role="alert">{error}</div> : null}

        <div className="readiness-actions">
          <button className="secondary-action" type="button" onClick={recheck} disabled={checking}>
            <ArrowClockwise className={checking ? 'spin' : ''} size={22} />
            {checking ? '检查中…' : checks.length ? '重新检查' : '开始检查'}
          </button>
          <button className="primary-action" type="button" onClick={startTask} disabled={checking || !ready}>
            <Play size={22} weight="fill" />开始面试
          </button>
        </div>
        <p className="gated-note"><LockKey size={15} />所有检查项必须通过后才能开始面试</p>
      </section>

      <aside className="phone-companion">
        <h2>{phoneConnected ? '手机端已配对' : activeTask.mobileRequired ? '等待手机端配对' : '手机端可选'}</h2>
        <p>{phoneConnected ? '建议回答会实时推送到手机' : activeTask.mobileRequired ? '请使用手机扫描下方二维码' : '可扫码连接，也可以只使用电脑端'}</p>
        <div className="qr-surface">
          {pairingUrl ? <QRCode
            bgColor="#ffffff"
            fgColor="#101d33"
            size={184}
            value={pairingUrl}
          /> : <span className="qr-loading">正在生成二维码…</span>}
        </div>
        <span className="qr-caption">扫描二维码查看手机端</span>
        <div className="phone-connection">
          <strong>手机连接状态</strong>
          <span className={phoneConnected ? '' : 'phone-offline'}><i />{phoneConnected ? '已连接' : '等待连接'}</span>
          <span className="phone-latency"><CellSignalFull size={21} weight="fill" />延迟 <em>35 ms</em></span>
        </div>
      </aside>
    </div>
  )
}
