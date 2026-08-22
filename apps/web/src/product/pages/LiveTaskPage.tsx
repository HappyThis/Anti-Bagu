import { Pause, Play, Stop } from '@phosphor-icons/react'
import { useState } from 'react'
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
  const { getTask, loading, updateTaskStatus } = useProduct()
  const { session } = useAuth()
  const task = getTask(taskId)
  const realtimeUrl = taskId && session
    ? websocketUrl(`/ws/tasks/${taskId}/ui`, session.token)
    : ''
  const { state, clear } = useRealtimeSession(realtimeUrl)
  const [paused, setPaused] = useState(false)

  if (loading) return <div className="route-loading">正在加载任务…</div>
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
          <span className="eyebrow">实时任务</span>
          <h1>{activeTask.name}</h1>
          <span className={`live-connection live-connection--${state.connection}`}>
            <i />{paused ? '已暂停采集' : state.connection === 'connected' ? '监听中' : '正在连接'}
          </span>
        </div>
        <div className="live-actions">
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
          title="面试官"
          source="系统音频"
          lines={state.interviewer}
          partial={state.partial.interviewer}
          connected={state.audioConnected.interviewer && !paused}
        />
        <TranscriptPanel
          channel="candidate"
          title="候选人"
          source="麦克风"
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
    </div>
  )
}
