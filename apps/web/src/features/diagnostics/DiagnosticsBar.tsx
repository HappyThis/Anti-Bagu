import type { LatencySnapshot } from '../../shared/protocol'

interface DiagnosticsBarProps {
  latency: LatencySnapshot
}

function value(milliseconds: number | null): string {
  return milliseconds === null ? '--' : `${Math.round(milliseconds)} ms`
}

export function DiagnosticsBar({ latency }: DiagnosticsBarProps) {
  const items = [
    ['系统音频', latency.systemAudio],
    ['麦克风', latency.microphone],
    ['ASR', latency.asr],
    ['模型', latency.model],
  ] as const

  return (
    <footer className="diagnostics-bar">
      <span className="diagnostics-title">延迟诊断</span>
      {items.map(([label, milliseconds]) => (
        <div className="diagnostic-item" key={label}>
          <span>{label}</span>
          <strong>{value(milliseconds)}</strong>
        </div>
      ))}
      <div className="diagnostic-total">
        <span>端到端延迟</span>
        <strong>{value(latency.endToEnd)}</strong>
      </div>
    </footer>
  )
}
