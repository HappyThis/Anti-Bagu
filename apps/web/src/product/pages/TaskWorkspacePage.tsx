import {
  ArrowClockwise,
  Check,
  CheckCircle,
  Desktop,
  DownloadSimple,
  Headphones,
  Microphone,
  Play,
  SpeakerHigh,
  VideoCamera,
  X,
} from '@phosphor-icons/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode, RefObject } from 'react'
import QRCode from 'react-qr-code'
import { Navigate, useNavigate } from 'react-router-dom'

import { apiRequest } from '../../shared/api'
import { useAuth } from '../AuthContext'
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

interface AudioTestLevel {
  rms: number
  peak: number
  at: number
}

interface AudioTestStatus {
  active: boolean
  agent_connected: boolean
  levels: Partial<Record<'interviewer' | 'candidate', AudioTestLevel>>
}

type AudioCheckPhase = 'intro' | 'starting' | 'system' | 'microphone' | 'verifying' | 'complete' | 'failed'

export function TaskWorkspacePage() {
  const navigate = useNavigate()
  const { session } = useAuth()
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
  const [preflightReady, setPreflightReady] = useState(false)
  const [pairingUrl, setPairingUrl] = useState('')
  const [phoneConnected, setPhoneConnected] = useState(false)
  const [error, setError] = useState('')
  const [audioCheckOpen, setAudioCheckOpen] = useState(false)
  const [audioCheckPhase, setAudioCheckPhase] = useState<AudioCheckPhase>('intro')
  const [audioLevels, setAudioLevels] = useState<AudioTestStatus['levels']>({})
  const [audioCheckError, setAudioCheckError] = useState('')
  const videoRef = useRef<HTMLVideoElement>(null)
  const systemHits = useRef(0)
  const microphoneHits = useRef(0)

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
    let disposed = false
    let timer: number | undefined
    setChecks([])
    setPreflightReady(false)
    async function refreshPreflight() {
      try {
        const result = await getPreflight(taskId as string)
        if (!disposed) {
          setChecks(result.checks)
          setPreflightReady(result.ready)
        }
      } catch {
        if (!disposed) {
          setChecks([])
          setPreflightReady(false)
        }
      } finally {
        if (!disposed) timer = window.setTimeout(refreshPreflight, 2_000)
      }
    }
    void refreshPreflight()
    return () => {
      disposed = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [getPreflight, taskId])

  useEffect(() => {
    if (nameDialog && !preflightReady) {
      setNameDialog(false)
      setError('')
    }
  }, [nameDialog, preflightReady])

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

  useEffect(() => {
    if (!taskId || !session || !audioCheckOpen || !['system', 'microphone'].includes(audioCheckPhase)) return
    let disposed = false
    let timer: number | undefined
    async function pollLevels() {
      try {
        const result = await apiRequest<AudioTestStatus>(`/tasks/${taskId}/audio-test`, {}, session?.token)
        if (disposed) return
        setAudioLevels(result.levels)
        if (!result.agent_connected) {
          setAudioCheckError('电脑助手已断开，请重新打开后再检测。')
          setAudioCheckPhase('failed')
          return
        }
        const now = Date.now() / 1000
        const system = result.levels.interviewer
        const microphone = result.levels.candidate
        if (audioCheckPhase === 'system') {
          systemHits.current = system && now - system.at < 1.5 && system.rms >= 0.008 ? systemHits.current + 1 : 0
          if (systemHits.current >= 3) {
            videoRef.current?.pause()
            setAudioCheckPhase('microphone')
          }
        } else {
          microphoneHits.current = microphone && now - microphone.at < 1.5 && microphone.rms >= 0.008 ? microphoneHits.current + 1 : 0
          if (microphoneHits.current >= 3) void finishAudioCheck()
        }
      } catch (requestError) {
        if (!disposed) {
          setAudioCheckError(requestError instanceof Error ? requestError.message : '无法读取声音检测结果')
          setAudioCheckPhase('failed')
        }
      } finally {
        if (!disposed) timer = window.setTimeout(pollLevels, 250)
      }
    }
    void pollLevels()
    return () => {
      disposed = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [audioCheckOpen, audioCheckPhase, session, taskId])

  const checkMap = useMemo(
    () => new Map(checks.map((check) => [check.key, check])),
    [checks],
  )

  async function refreshConnection() {
    if (!task) return
    setChecking(true)
    try {
      const result = await getPreflight(task.id)
      setChecks(result.checks)
      setPreflightReady(result.ready)
    } finally {
      setChecking(false)
    }
  }

  function openAudioCheck() {
    setAudioCheckOpen(true)
    setAudioCheckPhase('intro')
    setAudioCheckError('')
    setAudioLevels({})
    systemHits.current = 0
    microphoneHits.current = 0
  }

  async function startAudioCheck() {
    if (!task || !session) return
    setAudioCheckPhase('starting')
    setAudioCheckError('')
    setAudioLevels({})
    systemHits.current = 0
    microphoneHits.current = 0
    try {
      await apiRequest(`/tasks/${task.id}/audio-test/start`, { method: 'POST' }, session.token)
      setAudioCheckPhase('system')
    } catch (requestError) {
      setAudioCheckError(requestError instanceof Error ? requestError.message : '无法启动声音检测')
      setAudioCheckPhase('failed')
    }
  }

  async function playTestVideo() {
    const video = videoRef.current
    if (!video) return
    video.currentTime = 0
    try {
      await video.play()
    } catch {
      setAudioCheckError('浏览器没有允许播放声音，请再次点击播放。')
    }
  }

  async function finishAudioCheck() {
    if (!task || !session || audioCheckPhase === 'verifying') return
    setAudioCheckPhase('verifying')
    try {
      await apiRequest(`/tasks/${task.id}/audio-test/stop`, { method: 'POST' }, session.token)
      const result = await preflightTask(task.id)
      setChecks(result.checks)
      setPreflightReady(result.ready)
      if (result.ready) {
        setAudioCheckPhase('complete')
      } else {
        const failure = result.checks.find((check) => !check.ok)
        setAudioCheckError(failure?.detail ?? '还有一项服务没有准备好')
        setAudioCheckPhase('failed')
      }
    } catch (requestError) {
      setAudioCheckError(requestError instanceof Error ? requestError.message : '服务检查失败')
      setAudioCheckPhase('failed')
    }
  }

  async function closeAudioCheck() {
    videoRef.current?.pause()
    if (task && session && audioCheckPhase !== 'complete') {
      try {
        await apiRequest(`/tasks/${task.id}/audio-test/stop`, { method: 'POST' }, session.token)
      } catch {
        // Closing the dialog remains safe when the agent is already offline.
      }
    }
    setAudioCheckOpen(false)
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
  const computerReady = checkMap.get('agent')?.ok === true
  const soundKeys = ['system_audio', 'microphone', 'aec3', 'asr', 'llm']
  const soundReady = soundKeys.every((key) => checkMap.get(key)?.ok === true)
  const ready = preflightReady && computerReady && soundReady
  const currentStep = ready ? 3 : computerReady ? 2 : 1
  const firstProblem = checks.find((check) => !check.ok)

  return (
    <section className="interview-prep-page">
      <div className="prep-steps" aria-label="面试准备步骤">
        <PreparationStep number={1} title="打开电脑助手" description="下载并打开后会自动连接，无需了解复杂设置。" icon={<Desktop size={34} />} active={currentStep === 1} complete={computerReady} />

        <PreparationStep number={2} title="检查声音与回答" description="播放测试视频，再说一句话，确认两路声音和回答服务正常。" icon={<Headphones size={34} />} active={currentStep === 2} complete={soundReady} locked={!computerReady}>
          {computerReady && !ready ? <button className="primary-action prep-confirm" type="button" onClick={openAudioCheck}>开始检测</button> : null}
        </PreparationStep>

        <PreparationStep number={3} title="开始面试" description="一切准备好后，由你亲自点击开始。" icon={<Play size={34} weight="fill" />} active={currentStep === 3} complete={false} locked={!ready}>
          {ready ? <button className="primary-action prep-start" type="button" onClick={() => { setDraftName(''); setNameDialog(true) }}><Play size={21} weight="fill" />开始面试</button> : null}
        </PreparationStep>
      </div>

      {!computerReady ? <section className="helper-not-connected" aria-label="电脑助手未连接">
        <div><strong>电脑助手未连接</strong><span>可能尚未安装，或者安装后没有打开。</span><small>如果 macOS 提示“无法验证”，请前往“系统设置 → 隐私与安全性”，点击“仍要打开”。</small></div>
        <div className="helper-not-connected-actions"><a className="primary-action" href="/downloads/anti-bagu-agent-macos-arm64.tar.gz" download><DownloadSimple size={18} />尚未安装，立即下载</a><button className="secondary-action" type="button" onClick={() => void refreshConnection()} disabled={checking}><ArrowClockwise className={checking ? 'spin' : ''} size={18} />{checking ? '正在连接…' : '已经安装，重新连接'}</button></div>
      </section> : null}

      {firstProblem && firstProblem.key !== 'agent' ? <div className="prep-guidance" role="status"><span>{FAILURE_COPY[firstProblem.key] ?? '还有一项没有准备好'}</span><small>按当前步骤完成后，再点击确认。</small></div> : null}
      {error && !nameDialog ? <div className="form-error prep-error" role="alert">{error}</div> : null}

      {nameDialog ? <InterviewNameDialog name={draftName} pairingUrl={pairingUrl} phoneConnected={phoneConnected} saving={savingName} error={error} onChange={setDraftName} onCancel={() => { setNameDialog(false); setError('') }} onConfirm={() => void confirmName()} /> : null}
      {audioCheckOpen ? <AudioCheckDialog phase={audioCheckPhase} levels={audioLevels} error={audioCheckError} videoRef={videoRef} onStart={() => void startAudioCheck()} onPlay={() => void playTestVideo()} onClose={() => void closeAudioCheck()} /> : null}
    </section>
  )
}

function AudioCheckDialog({
  phase,
  levels,
  error,
  videoRef,
  onStart,
  onPlay,
  onClose,
}: {
  phase: AudioCheckPhase
  levels: AudioTestStatus['levels']
  error: string
  videoRef: RefObject<HTMLVideoElement | null>
  onStart: () => void
  onPlay: () => void
  onClose: () => void
}) {
  const systemPassed = ['microphone', 'verifying', 'complete'].includes(phase)
  const microphonePassed = ['verifying', 'complete'].includes(phase)
  return (
    <div className="dialog-backdrop" role="presentation">
      <section className="audio-check-dialog" role="dialog" aria-modal="true" aria-labelledby="audio-check-title">
        <button className="dialog-close" type="button" aria-label="关闭声音检测" onClick={onClose}><X size={20} /></button>
        <span className="eyebrow">声音与回答检查</span>
        <h2 id="audio-check-title">确认电脑真的听得见</h2>
        <p>先检测页面播放的面试声音，再检测你对着麦克风说话。</p>
        <div className="audio-check-grid">
          <div className={`audio-check-stage ${phase === 'system' ? 'audio-check-stage--active' : ''} ${systemPassed ? 'audio-check-stage--passed' : ''}`}>
            <header><span><SpeakerHigh size={20} />面试声音</span>{systemPassed ? <CheckCircle size={19} weight="fill" /> : null}</header>
            <div className="audio-test-video">
              <video ref={videoRef} src="/media/audio-check.mp4" playsInline onEnded={() => undefined} />
              <span><VideoCamera size={24} />Anti-Bagu Audio Check</span>
            </div>
            <AudioLevelBar label="系统音频信号" level={levels.interviewer} passed={systemPassed} />
            {phase === 'system' ? <button className="secondary-action compact-action" type="button" onClick={onPlay}><Play size={17} weight="fill" />播放测试视频</button> : null}
          </div>
          <div className={`audio-check-stage ${phase === 'microphone' ? 'audio-check-stage--active' : ''} ${microphonePassed ? 'audio-check-stage--passed' : ''}`}>
            <header><span><Microphone size={20} />我的声音</span>{microphonePassed ? <CheckCircle size={19} weight="fill" /> : null}</header>
            <div className="microphone-prompt"><Microphone size={30} weight="duotone" /><strong>{phase === 'microphone' ? '请说一句话' : '等待麦克风检测'}</strong><span>例如：“这是一次声音测试”</span></div>
            <AudioLevelBar label="麦克风信号" level={levels.candidate} passed={microphonePassed} />
          </div>
        </div>
        {phase === 'intro' ? <div className="audio-check-callout">检测期间不会把声音发送给 ASR，也不会生成面试记录。</div> : null}
        {phase === 'starting' || phase === 'verifying' ? <div className="audio-check-progress"><ArrowClockwise className="spin" size={18} />{phase === 'starting' ? '正在启动双路声音检测…' : '声音正常，正在检查 AEC3、问题识别和回答服务…'}</div> : null}
        {phase === 'complete' ? <div className="inline-success"><CheckCircle size={19} weight="fill" />声音与回答功能均已准备好。</div> : null}
        {error ? <div className="form-error" role="alert">{error}</div> : null}
        <div className="dialog-actions">
          {phase === 'failed' && error.includes('版本过旧') ? <a className="secondary-action" href="/downloads/anti-bagu-agent-macos-arm64.tar.gz" download><DownloadSimple size={17} />下载最新版</a> : null}
          <button className="secondary-action" type="button" onClick={onClose}>{phase === 'complete' ? '完成' : '取消'}</button>
          {phase === 'intro' || phase === 'failed' ? <button className="primary-action" type="button" onClick={onStart}>{phase === 'failed' ? '重新检测' : '启动检测'}</button> : null}
        </div>
      </section>
    </div>
  )
}

function AudioLevelBar({ label, level, passed }: { label: string; level?: AudioTestLevel; passed: boolean }) {
  const strength = Math.min(100, Math.max(2, (level?.rms ?? 0) * 700))
  const hot = (level?.peak ?? 0) >= 0.95
  return <div className="audio-check-level"><div><span>{label}</span><em>{passed ? '已通过' : `${Math.round(strength)}%`}</em></div><i><b className={hot ? 'audio-check-level--hot' : ''} style={{ width: `${strength}%` }} /></i></div>
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
