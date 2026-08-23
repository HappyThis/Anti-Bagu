import { DeviceMobile, Pause, Play, Stop, X } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import QRCode from 'react-qr-code'
import { Navigate, useNavigate, useParams } from 'react-router-dom'

import { AnswerWorkspace } from '../../features/answer/AnswerWorkspace'
import { DiagnosticsBar } from '../../features/diagnostics/DiagnosticsBar'
import { useRealtimeSession } from '../../features/session/useRealtimeSession'
import { TranscriptPanel } from '../../features/transcript/TranscriptPanel'
import { websocketUrl } from '../../shared/api'
import { useAuth } from '../AuthContext'
import { useProduct } from '../ProductContext'

export function LiveTaskPage() {
  const { taskId } = useParams()
  const navigate = useNavigate()
  const { getTask, getPairing, loading, updateTaskStatus } = useProduct()
  const { session } = useAuth()
  const task = getTask(taskId)
  const realtimeUrl = taskId && session
    ? websocketUrl(`/ws/tasks/${taskId}/ui`, session.token)
    : ''
  const { state, clear } = useRealtimeSession(realtimeUrl)
  const [paused, setPaused] = useState(false)
  const [showPhone, setShowPhone] = useState(false)
  const [pairingUrl, setPairingUrl] = useState('')
  const [phoneConnected, setPhoneConnected] = useState(false)

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

  if (loading) return <div className="route-loading">正在加载面试…</div>
  if (!task) return <Navigate to="/tasks" replace />
  const activeTask = task

  async function togglePause() {
    const next = !paused
    setPaused(next)
    try {
      await updateTaskStatus(activeTask.id, next ? 'paused' : 'running')
    } catch {
      setPaused(!next)
    }
  }

  async function endTask() {
    await updateTaskStatus(activeTask.id, 'completed')
    navigate('/reviews')
  }

  return (
    <div className="live-page">
      <header className="live-header">
        <div>
          <span className="eyebrow">面试进行中</span>
          <h1>{activeTask.name}</h1>
          <span className={`live-connection live-connection--${state.connection}`}>
            <i />{paused ? '已暂停' : state.connection === 'connected' ? '正在听取面试' : '正在连接电脑助手'}
          </span>
        </div>
        <div className="live-actions">
          <button className={`secondary-action live-phone-action ${phoneConnected ? 'live-phone-action--connected' : ''}`} type="button" onClick={() => setShowPhone(true)}>
            <DeviceMobile size={19} />{phoneConnected ? '手机已连接' : '手机二维码'}
          </button>
          <button className="secondary-action" type="button" onClick={togglePause}>
            {paused ? <Play size={19} weight="fill" /> : <Pause size={19} weight="fill" />}
            {paused ? '继续' : '暂停'}
          </button>
          <button className="danger-action" type="button" onClick={endTask}>
            <Stop size={19} weight="fill" />结束任务
          </button>
        </div>
      </header>

      <div className="live-transcript-grid">
        <TranscriptPanel
          channel="interviewer"
          title="面试官说的话"
          source="面试声音"
          lines={state.interviewer}
          partial={state.partial.interviewer}
          connected={state.audioConnected.interviewer && !paused}
        />
        <TranscriptPanel
          channel="candidate"
          title="我说的话"
          source="我的声音"
          lines={state.candidate}
          partial={state.partial.candidate}
          connected={state.audioConnected.candidate && !paused}
        />
      </div>

      <AnswerWorkspace
        focus={state.focus}
        answer={state.answer}
        mode={state.answerMode}
        generating={state.generating}
        error={state.error}
        onClear={clear}
      />
      <DiagnosticsBar latency={state.latency} />
      {showPhone ? <PhonePairingDialog pairingUrl={pairingUrl} connected={phoneConnected} onClose={() => setShowPhone(false)} /> : null}
    </div>
  )
}

function PhonePairingDialog({ pairingUrl, connected, onClose }: { pairingUrl: string; connected: boolean; onClose: () => void }) {
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section className="phone-pairing-dialog" role="dialog" aria-modal="true" aria-labelledby="phone-pairing-title">
        <button className="dialog-close" type="button" aria-label="关闭手机二维码" onClick={onClose}><X size={20} /></button>
        <span className="dialog-phone-icon"><DeviceMobile size={25} /></span>
        <h2 id="phone-pairing-title">用手机查看回答</h2>
        <p>使用手机扫码，打开后保持页面在线即可。</p>
        <div className="qr-surface">{pairingUrl ? <QRCode bgColor="#ffffff" fgColor="#101d33" size={184} value={pairingUrl} /> : <span className="qr-loading">正在生成二维码…</span>}</div>
        <em className={connected ? 'paired-state' : ''}>{connected ? '手机已连接' : '等待手机连接'}</em>
      </section>
    </div>
  )
}
