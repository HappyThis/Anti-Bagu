import type { LatencySnapshot } from '../../shared/protocol'

interface DiagnosticsBarProps {
  latency: LatencySnapshot
}

function value(milliseconds: number | null): string {
  return milliseconds === null ? '--' : `${Math.round(milliseconds)} ms`
}

export function DiagnosticsBar({ latency }: DiagnosticsBarProps) {
  const items = [
    ['面试声音', latency.systemAudio],
    ['我的声音', latency.microphone],
    ['问题识别', latency.asr],
    ['回答生成', latency.model],
  ] as const

  return (
    <footer className="diagnostics-bar">
      <span className="diagnostics-title">响应情况</span>
      {items.map(([label, milliseconds]) => (
        <div className="diagnostic-item" key={label}>
          <span>{label}</span>
          <strong>{value(milliseconds)}</strong>
        </div>
      ))}
      <div className="diagnostic-total">
        <span>整体响应</span>
        <strong>{value(latency.endToEnd)}</strong>
      </div>
    </footer>
  )
}
