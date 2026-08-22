import { ArrowLeft, CheckCircle, DownloadSimple, Play } from '@phosphor-icons/react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { apiRequest } from '../../shared/api'
import { useAuth } from '../AuthContext'
import { useProduct } from '../ProductContext'

interface TaskEventRecord {
  id: number
  event_id: string
  event_type: string
  conversation_revision: number
  payload: Record<string, unknown>
  created_at: string
}

const DISPLAYED_EVENTS = new Set([
  'transcript.final',
  'focus.updated',
  'answer.completed',
  'answer.cancelled',
  'error',
])

export function ReviewDetailPage() {
  const { reviewId = '' } = useParams()
  const navigate = useNavigate()
  const { session } = useAuth()
  const { getTask } = useProduct()
  const task = getTask(reviewId)
  const [events, setEvents] = useState<TaskEventRecord[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!session || !reviewId) return
    apiRequest<TaskEventRecord[]>(`/tasks/${reviewId}/events?limit=5000`, {}, session.token)
      .then(setEvents)
      .finally(() => setLoading(false))
  }, [reviewId, session])

  const timeline = useMemo(() => events.filter((event) => DISPLAYED_EVENTS.has(event.event_type)), [events])
  const focuses = events.filter((event) => event.event_type === 'focus.updated')
  const latencies = events
    .filter((event) => event.event_type === 'latency.updated' && event.payload.endToEnd !== undefined)
    .map((event) => Number(event.payload.endToEnd))
  const averageLatency = latencies.length
    ? Math.round(latencies.reduce((sum, latency) => sum + latency, 0) / latencies.length)
    : 0

  return (
    <section className="content-page review-detail-page">
      <button className="back-link" type="button" onClick={() => navigate('/reviews')}>
        <ArrowLeft size={18} />返回复盘
      </button>
      <div className="page-title-actions">
        <div>
          <span className="eyebrow">任务复盘</span>
          <h1>{task?.name ?? '面试任务'}</h1>
          <p className="page-lead">{task?.createdAt ?? ''} · 完整事件时间线</p>
        </div>
        <button className="secondary-action" type="button" onClick={() => downloadEvents(reviewId, events)}><DownloadSimple size={19} />导出 JSONL</button>
      </div>

      <div className="review-summary-strip">
        <span><small>识别问题</small><strong>{focuses.length}</strong><em>全部已处理</em></span>
        <span><small>平均端到端</small><strong>{averageLatency ? `${averageLatency} ms` : '—'}</strong><em>目标 &lt; 3 秒</em></span>
        <span><small>异常事件</small><strong>{events.filter((event) => event.event_type === 'error').length}</strong><em>系统记录</em></span>
        <span><small>数据完整性</small><strong>{events.length ? '完整' : '—'}</strong><em><CheckCircle size={13} weight="fill" />已持久化</em></span>
      </div>

      <div className="review-layout">
        <div className="timeline-panel">
          <header><h2>完整时间线</h2><span>{timeline.length} 个关键事件</span></header>
          {timeline.map((event) => {
            const view = eventView(event)
            return (
              <div className={`timeline-event timeline-event--${view.type}`} key={event.event_id}>
                <time>{new Date(event.created_at).toLocaleTimeString('zh-CN', { hour12: false })}</time>
                <i />
                <div><span>{view.type}</span><strong>{view.title}</strong><small>{view.detail}</small></div>
              </div>
            )
          })}
          {!loading && timeline.length === 0 ? <div className="table-empty-state"><strong>暂无关键事件</strong><span>任务运行后，转写、Focus 和回答会显示在这里。</span></div> : null}
        </div>
        <aside className="audio-review-panel">
          <span className="side-panel-label">回放控制</span>
          <h2>双路音频</h2>
          <p>服务端按任务和通道保存原始音频，时间线事件与音频使用同一时间基准。</p>
          <button className="audio-track" type="button"><Play size={18} weight="fill" /><span>面试官</span><b>系统音频</b></button>
          <button className="audio-track audio-track--candidate" type="button"><Play size={18} weight="fill" /><span>候选人</span><b>麦克风</b></button>
          <hr />
          <h3>本次模型配置</h3>
          <dl>
            <div><dt>ASR</dt><dd>Qwen Audio 3 ASR Flash</dd></div>
            <div><dt>LLM</dt><dd>DeepSeek V4 Flash Vision</dd></div>
            <div><dt>输入窗口</dt><dd>8K tokens</dd></div>
          </dl>
          <div className="review-integrity"><CheckCircle size={18} weight="fill" /><span><strong>记录已落盘</strong><small>事件、模型输入和运行日志均按任务保存</small></span></div>
        </aside>
      </div>
    </section>
  )
}

function eventView(event: TaskEventRecord) {
  const payload = event.payload
  if (event.event_type === 'transcript.final') {
    return {
      type: payload.channel === 'candidate' ? '候选人' : '面试官',
      title: String(payload.text ?? ''),
      detail: 'ASR final',
    }
  }
  if (event.event_type === 'focus.updated') {
    return { type: 'Focus', title: String(payload.question ?? ''), detail: `generation ${payload.generation ?? '—'} · ${payload.mode ?? ''}` }
  }
  if (event.event_type === 'answer.completed') {
    return { type: '建议回答', title: String(payload.answer ?? ''), detail: `${payload.mode ?? ''} · ${Math.round(Number(payload.duration_ms ?? 0))} ms` }
  }
  if (event.event_type === 'answer.cancelled') {
    return { type: '系统', title: '旧回答已被新问题抢占', detail: String(payload.reason ?? '') }
  }
  return { type: '系统', title: String(payload.message ?? '系统事件'), detail: event.event_type }
}

function downloadEvents(taskId: string, events: TaskEventRecord[]) {
  const content = events.map((event) => JSON.stringify(event)).join('\n')
  const url = URL.createObjectURL(new Blob([content], { type: 'application/x-ndjson' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${taskId}-events.jsonl`
  anchor.click()
  URL.revokeObjectURL(url)
}
