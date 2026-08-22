import {
  ArrowClockwise,
  Check,
  Desktop,
  DeviceMobile,
  DownloadSimple,
  Headphones,
  LockKey,
  PencilSimple,
  Play,
} from '@phosphor-icons/react'
import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import QRCode from 'react-qr-code'
import { Navigate, useNavigate, useParams } from 'react-router-dom'

import { useProduct } from '../ProductContext'
import type { PreflightCheck } from '../types'

const FAILURE_COPY: Record<string, string> = {
  agent: '电脑助手还没有连接',
  agent_response: '电脑助手暂时没有响应',
  system_audio: '暂时听不到面试声音',
  microphone: '暂时听不到你的声音',
  asr: '问题识别功能还没有准备好',
  llm: '回答功能还没有准备好',
  mobile: '请先连接手机',
}

export function TaskWorkspacePage() {
  const { taskId } = useParams()
  const navigate = useNavigate()
  const {
    getTask,
    loading,
    renameTask,
    updateTaskStatus,
    preflightTask,
    getPreflight,
    getPairing,
  } = useProduct()
  const task = getTask(taskId)
  const [checking, setChecking] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [draftName, setDraftName] = useState(task?.name ?? '')
  const [checks, setChecks] = useState<PreflightCheck[]>([])
  const [pairingUrl, setPairingUrl] = useState('')
  const [phoneConnected, setPhoneConnected] = useState(false)
  const [showPhone, setShowPhone] = useState(false)
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
    getPreflight(taskId)
      .then((result) => setChecks(result.checks))
      .catch(() => setChecks([]))
  }, [getPreflight, taskId])

  const checkMap = useMemo(
    () => new Map(checks.map((check) => [check.key, check])),
    [checks],
  )

  if (loading) return <div className="route-loading">正在加载面试…</div>
  if (!task) return <Navigate to="/tasks" replace />
  const activeTask = task
  const ready = activeTask.status === 'ready'
  const computerReady = checkMap.get('agent')?.ok === true
  const soundKeys = ['system_audio', 'microphone', 'asr', 'llm']
  const soundReady = soundKeys.every((key) => checkMap.get(key)?.ok === true)
  const currentStep = ready ? 3 : computerReady ? 2 : 1
  const firstProblem = checks.find((check) => !check.ok)
  const progress = ready ? 3 : soundReady ? 2 : computerReady ? 1 : 0

  async function confirmReadiness() {
    setChecking(true)
    setError('')
    try {
      const result = await preflightTask(activeTask.id)
      setChecks(result.checks)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '暂时无法完成确认，请稍后重试')
    } finally {
      setChecking(false)
    }
  }

  async function saveName() {
    const name = draftName.trim()
    if (name) await renameTask(activeTask.id, name)
    setRenaming(false)
  }

  async function startInterview() {
    setError('')
    try {
      await updateTaskStatus(activeTask.id, 'running')
      navigate(`/tasks/${activeTask.id}/live`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '暂时无法开始，请重新确认')
    }
  }

  return (
    <section className="interview-prep-page">
      <header className="prep-header">
        <span className="eyebrow">准备面试</span>
        <div className="task-title-row task-title-row--centered">
          {renaming ? (
            <div className="rename-control">
              <input autoFocus value={draftName} onChange={(event) => setDraftName(event.target.value)} onKeyDown={(event) => {
                if (event.key === 'Enter') void saveName()
                if (event.key === 'Escape') setRenaming(false)
              }} />
              <button type="button" onClick={() => void saveName()}>保存</button>
            </div>
          ) : (
            <><h1>准备{activeTask.name}</h1><button className="rename-button" type="button" onClick={() => { setDraftName(activeTask.name); setRenaming(true) }}><PencilSimple size={18} />修改名称</button></>
          )}
        </div>
        <p>三步完成准备，轻松开启面试。</p>
        <strong className="prep-progress">完成 <b>{progress}</b> / 3</strong>
      </header>

      <div className="prep-steps" aria-label="面试准备步骤">
        <PreparationStep number={1} title="打开电脑助手" description="下载并打开后会自动连接，无需了解复杂设置。" icon={<Desktop size={34} />} active={currentStep === 1} complete={computerReady} />

        <PreparationStep number={2} title="确认可以听清" description="确认面试声音、你的声音和回答功能都能正常使用。" icon={<Headphones size={34} />} active={currentStep === 2} complete={soundReady} locked={!computerReady}>
          {computerReady && !ready ? <button className="primary-action prep-confirm" type="button" onClick={() => void confirmReadiness()} disabled={checking}>{checking ? <><ArrowClockwise className="spin" size={19} />正在确认…</> : '开始确认'}</button> : null}
        </PreparationStep>

        <PreparationStep number={3} title="开始面试" description="一切准备好后，由你亲自点击开始。" icon={<Play size={34} weight="fill" />} active={currentStep === 3} complete={false} locked={!ready}>
          {ready ? <button className="primary-action prep-start" type="button" onClick={() => void startInterview()}><Play size={21} weight="fill" />开始面试</button> : null}
        </PreparationStep>
      </div>

      {!computerReady ? <section className="helper-not-connected" aria-label="电脑助手未连接">
        <div><strong>电脑助手未连接</strong><span>可能尚未安装，或者安装后没有打开。</span><small>如果 macOS 提示“无法验证”，请前往“系统设置 → 隐私与安全性”，点击“仍要打开”。</small></div>
        <div className="helper-not-connected-actions"><a className="primary-action" href="/downloads/anti-bagu-agent-macos-arm64.tar.gz" download><DownloadSimple size={18} />尚未安装，立即下载</a><button className="secondary-action" type="button" onClick={() => void confirmReadiness()} disabled={checking}><ArrowClockwise className={checking ? 'spin' : ''} size={18} />{checking ? '正在连接…' : '已经安装，重新连接'}</button></div>
      </section> : null}

      {firstProblem && firstProblem.key !== 'agent' ? <div className="prep-guidance" role="status"><span>{FAILURE_COPY[firstProblem.key] ?? '还有一项没有准备好'}</span><small>按当前步骤完成后，再点击确认。</small></div> : null}
      {error ? <div className="form-error prep-error" role="alert">{error}</div> : null}

      <div className="phone-setup-row">
        <DeviceMobile size={28} />
        <div><strong>想在手机上看回答？</strong><span>{phoneConnected ? '手机已经连接，面试开始后会同步显示回答。' : '连接后，可以在手机上实时查看回答内容。'}</span></div>
        <button className="secondary-action compact-action" type="button" onClick={() => setShowPhone((current) => !current)}>{phoneConnected ? '查看二维码' : '连接手机'}</button>
      </div>
      {showPhone ? <div className="inline-phone-pairing"><div className="qr-surface">{pairingUrl ? <QRCode bgColor="#ffffff" fgColor="#101d33" size={184} value={pairingUrl} /> : <span className="qr-loading">正在生成二维码…</span>}</div><div><strong>用手机扫码</strong><span>打开后保持页面在线即可。</span><em className={phoneConnected ? 'paired-state' : ''}>{phoneConnected ? '已连接' : '等待连接'}</em></div></div> : null}
      <p className="gated-note"><LockKey size={15} />只有你点击“开始面试”后，电脑助手才会开始工作</p>
    </section>
  )
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
