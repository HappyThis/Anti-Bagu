import type { Channel, TranscriptLine } from '../../shared/protocol'
import { AudioWaveform } from './AudioWaveform'

interface TranscriptPanelProps {
  channel: Channel
  title: string
  source: string
  lines: TranscriptLine[]
  partial: string
  connected: boolean
}

function displayTime(createdAt: number): string {
  if (createdAt < 10_000) return '--:--:--'
  return new Date(createdAt * 1000).toLocaleTimeString('zh-CN', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function TranscriptPanel({
  channel,
  title,
  source,
  lines,
  partial,
  connected,
}: TranscriptPanelProps) {
  const empty = lines.length === 0 && !partial
  return (
    <section className={`transcript-panel transcript-panel--${channel}`}>
      <header className="panel-header">
        <div>
          <h2>{title}</h2>
          <span>{source} · {connected ? '实时采集' : '等待连接'}</span>
        </div>
        <AudioWaveform channel={channel} connected={connected} />
      </header>
      <div className="transcript-list" aria-live="polite">
        {empty ? (
          <p className="empty-copy">等待语音输入…</p>
        ) : (
          lines.map((line) => (
            <div className="transcript-line" key={line.id}>
              <time>{displayTime(line.createdAt)}</time>
              <p>{line.text}</p>
            </div>
          ))
        )}
        {partial ? (
          <div className="transcript-line transcript-line--partial">
            <time>实时</time>
            <p>{partial}</p>
          </div>
        ) : null}
      </div>
    </section>
  )
}
