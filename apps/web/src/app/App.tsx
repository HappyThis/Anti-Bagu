import { AnswerWorkspace } from '../features/answer/AnswerWorkspace'
import { DiagnosticsBar } from '../features/diagnostics/DiagnosticsBar'
import { useRealtimeSession } from '../features/session/useRealtimeSession'
import { TranscriptPanel } from '../features/transcript/TranscriptPanel'

const REALTIME_URL = import.meta.env.VITE_REALTIME_URL ?? 'ws://127.0.0.1:8765/ws/ui'

const statusCopy = {
  connecting: '连接中',
  connected: '监听中',
  disconnected: '已断开',
} as const

export function App() {
  const { state, clear } = useRealtimeSession(REALTIME_URL)

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">Anti-Bagu</div>
        <div className={`connection-state connection-state--${state.connection}`}>
          <span />
          {statusCopy[state.connection]}
        </div>
        <div className="topbar-meta">
          <span>本地模式</span>
          <span>实时转写</span>
        </div>
      </header>

      <div className="transcript-grid">
        <TranscriptPanel
          channel="interviewer"
          title="面试官"
          source="系统音频"
          lines={state.interviewer}
          partial={state.partial.interviewer}
          connected={state.audioConnected.interviewer}
        />
        <TranscriptPanel
          channel="candidate"
          title="候选人"
          source="麦克风"
          lines={state.candidate}
          partial={state.partial.candidate}
          connected={state.audioConnected.candidate}
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
    </main>
  )
}
