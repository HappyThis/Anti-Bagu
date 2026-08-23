import {
  ArrowClockwise,
  Check,
  Desktop,
  DownloadSimple,
  Headphones,
  Play,
} from '@phosphor-icons/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import QRCode from 'react-qr-code'
import { Navigate, useNavigate } from 'react-router-dom'

import { useProduct } from '../ProductContext'
import type { PreflightCheck } from '../types'

const FAILURE_COPY: Record<string, string> = {
  agent: '电脑助手还没有连接',
  agent_response: '电脑助手暂时没有响应',
  system_audio: '暂时听不到面试声音',
  microphone: '暂时听不到你的声音',
  aec3: '麦克风回声消除还没有准备好',
  asr: '问题识别功能还没有准备好',
  llm: '回答功能还没有准备好',
  mobile: '请先连接手机',
}

export function TaskWorkspacePage() {
  const navigate = useNavigate()
  const {
    tasks,
    loading,
    createTask,
    renameTask,
    updateTaskStatus,
    preflightTask,
    getPreflight,
    getPairing,
  } = useProduct()
  const task = useMemo(
    () => tasks.find((item) => item.status !== 'completed'),
    [tasks],
  )
  const taskId = task?.id
  const creatingTaskRef = useRef(false)
  const [checking, setChecking] = useState(false)
  const [nameDialog, setNameDialog] = useState(false)
  const [draftName, setDraftName] = useState('')
  const [savingName, setSavingName] = useState(false)
  const [checks, setChecks] = useState<PreflightCheck[]>([])
  const [pairingUrl, setPairingUrl] = useState('')
  const [phoneConnected, setPhoneConnected] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (loading || task || creatingTaskRef.current) return
    creatingTaskRef.current = true
    setError('')
    createTask(defaultInterviewName())
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : '暂时无法准备面试，请刷新后重试')
        creatingTaskRef.current = false
      })
  }, [createTask, loading, task])

  useEffect(() => {
    if (!taskId) return
    getPreflight(taskId)
      .then((result) => setChecks(result.checks))
      .catch(() => setChecks([]))
  }, [getPreflight, taskId])

  useEffect(() => {
    if (!taskId || !nameDialog) return
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
  }, [getPairing, nameDialog, taskId])

  const checkMap = useMemo(
    () => new Map(checks.map((check) => [check.key, check])),
    [checks],
  )

  async function confirmReadiness() {
    if (!task) return
    setChecking(true)
    setError('')
    try {
      const result = await preflightTask(task.id)
      setChecks(result.checks)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '暂时无法完成确认，请稍后重试')
    } finally {
      setChecking(false)
    }
  }

  async function confirmName() {
    const name = draftName.trim()
    if (!name) return
    setSavingName(true)
    setError('')
    try {
      if (!task) return
      if (name !== task.name) await renameTask(task.id, name)
      await updateTaskStatus(task.id, 'running')
      navigate(`/tasks/${task.id}/live`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '暂时无法继续，请稍后重试')
    } finally {
      setSavingName(false)
    }
  }

  if (loading) return <div className="route-loading">正在加载面试…</div>
  if (!task) return <div className="route-loading">{error || '正在准备面试…'}</div>
  const activeTask = task
  if (activeTask.status === 'running') return <Navigate to={`/tasks/${activeTask.id}/live`} replace />
  const ready = activeTask.status === 'ready'
  const computerReady = checkMap.get('agent')?.ok === true
  const soundKeys = ['system_audio', 'microphone', 'aec3', 'asr', 'llm']
  const soundReady = soundKeys.every((key) => checkMap.get(key)?.ok === true)
  const currentStep = ready ? 3 : computerReady ? 2 : 1
  const firstProblem = checks.find((check) => !check.ok)

  return (
    <section className="interview-prep-page">
      <div className="prep-steps" aria-label="面试准备步骤">
        <PreparationStep number={1} title="打开电脑助手" description="下载并打开后会自动连接，无需了解复杂设置。" icon={<Desktop size={34} />} active={currentStep === 1} complete={computerReady} />

        <PreparationStep number={2} title="确认可以听清" description="确认面试声音、你的声音和回答功能都能正常使用。" icon={<Headphones size={34} />} active={currentStep === 2} complete={soundReady} locked={!computerReady}>
          {computerReady && !ready ? <button className="primary-action prep-confirm" type="button" onClick={() => void confirmReadiness()} disabled={checking}>{checking ? <><ArrowClockwise className="spin" size={19} />正在确认…</> : '开始确认'}</button> : null}
        </PreparationStep>

        <PreparationStep number={3} title="开始面试" description="一切准备好后，由你亲自点击开始。" icon={<Play size={34} weight="fill" />} active={currentStep === 3} complete={false} locked={!ready}>
          {ready ? <button className="primary-action prep-start" type="button" onClick={() => { setDraftName(''); setNameDialog(true) }}><Play size={21} weight="fill" />开始面试</button> : null}
        </PreparationStep>
      </div>

      {!computerReady ? <section className="helper-not-connected" aria-label="电脑助手未连接">
        <div><strong>电脑助手未连接</strong><span>可能尚未安装，或者安装后没有打开。</span><small>如果 macOS 提示“无法验证”，请前往“系统设置 → 隐私与安全性”，点击“仍要打开”。</small></div>
        <div className="helper-not-connected-actions"><a className="primary-action" href="/downloads/anti-bagu-agent-macos-arm64.tar.gz" download><DownloadSimple size={18} />尚未安装，立即下载</a><button className="secondary-action" type="button" onClick={() => void confirmReadiness()} disabled={checking}><ArrowClockwise className={checking ? 'spin' : ''} size={18} />{checking ? '正在连接…' : '已经安装，重新连接'}</button></div>
      </section> : null}

      {firstProblem && firstProblem.key !== 'agent' ? <div className="prep-guidance" role="status"><span>{FAILURE_COPY[firstProblem.key] ?? '还有一项没有准备好'}</span><small>按当前步骤完成后，再点击确认。</small></div> : null}
      {error && !nameDialog ? <div className="form-error prep-error" role="alert">{error}</div> : null}

      {nameDialog ? <InterviewNameDialog name={draftName} pairingUrl={pairingUrl} phoneConnected={phoneConnected} saving={savingName} error={error} onChange={setDraftName} onCancel={() => { setNameDialog(false); setError('') }} onConfirm={() => void confirmName()} /> : null}
    </section>
  )
}

function InterviewNameDialog({
  name,
  pairingUrl,
  phoneConnected,
  saving,
  error,
  onChange,
  onCancel,
  onConfirm,
}: {
  name: string
  pairingUrl: string
  phoneConnected: boolean
  saving: boolean
  error: string
  onChange: (name: string) => void
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel() }}>
      <section className="interview-name-dialog interview-name-dialog--with-phone" role="dialog" aria-modal="true" aria-labelledby="interview-name-title">
        <div className="interview-name-dialog-grid">
          <div className="interview-name-form">
            <span className="eyebrow">最后一步</span>
            <h2 id="interview-name-title">确认面试名称</h2>
            <p>这个名称只用于之后查找面试记录。</p>
            <label><span>面试名称</span><input autoFocus value={name} placeholder="例如：字节跳动后端二面" onChange={(event) => onChange(event.target.value)} onKeyDown={(event) => {
              if (event.key === 'Enter' && name.trim()) onConfirm()
              if (event.key === 'Escape') onCancel()
            }} /></label>
            {error ? <div className="form-error" role="alert">{error}</div> : null}
          </div>
          <aside className="interview-name-phone" aria-label="手机二维码">
            <strong>手机查看回答</strong>
            <span>扫码后保持页面在线</span>
            <div className="qr-surface">{pairingUrl ? <QRCode bgColor="#ffffff" fgColor="#101d33" size={154} value={pairingUrl} /> : <span className="qr-loading">正在生成二维码…</span>}</div>
            <em className={phoneConnected ? 'paired-state' : ''}>{phoneConnected ? '手机已连接' : '等待手机连接'}</em>
          </aside>
        </div>
        <div className="dialog-actions"><button className="secondary-action" type="button" onClick={onCancel}>取消</button><button className="primary-action" type="button" disabled={!name.trim() || saving} onClick={onConfirm}>{saving ? '正在处理…' : '确认并开始'}</button></div>
      </section>
    </div>
  )
}

function defaultInterviewName() {
  const now = new Date()
  const date = now.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }).replaceAll('/', '-')
  const time = now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
  return `面试 ${date} ${time}`
}

function PreparationStep({
  number,
  title,
  description,
  icon,
  active,
  complete,
  locked = false,
  children,
}: {
  number: number
  title: string
  description: string
  icon: ReactNode
  active: boolean
  complete: boolean
  locked?: boolean
  children?: ReactNode
}) {
  return (
    <article className={`prep-step ${active ? 'prep-step--active' : ''} ${complete ? 'prep-step--complete' : ''} ${locked ? 'prep-step--locked' : ''}`}>
      <div className="prep-step-icon">{complete ? <Check size={34} weight="bold" /> : icon}</div>
      <span className="prep-step-number">{number}</span>
      <h2>{title}</h2>
      <p>{description}</p>
      {children ? <div className="prep-step-action">{children}</div> : null}
    </article>
  )
}
