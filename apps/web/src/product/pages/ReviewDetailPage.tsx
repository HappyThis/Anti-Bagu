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
  const answers = events.filter((event) => event.event_type === 'answer.completed')
  const interrupted = events.filter((event) => event.event_type === 'answer.cancelled')

  return (
    <section className="content-page review-detail-page">
      <button className="back-link" type="button" onClick={() => navigate('/reviews')}>
        <ArrowLeft size={18} />返回面试记录
      </button>
      <div className="page-title-actions">
        <div>
          <span className="eyebrow">面试记录</span>
          <h1>{task?.name ?? '面试'}</h1>
          <p className="page-lead">{task?.createdAt ?? ''} · 按时间回顾问题和回答</p>
        </div>
        <button className="secondary-action" type="button" onClick={() => downloadEvents(reviewId, events)}><DownloadSimple size={19} />导出记录</button>
      </div>

      <div className="review-summary-strip">
        <span><small>面试问题</small><strong>{focuses.length}</strong><em>自动整理</em></span>
        <span><small>建议回答</small><strong>{answers.length}</strong><em>已保存</em></span>
        <span><small>回答切换</small><strong>{interrupted.length}</strong><em>遇到新问题</em></span>
        <span><small>记录状态</small><strong>{events.length ? '完整' : '—'}</strong><em><CheckCircle size={13} weight="fill" />可以查看</em></span>
      </div>

      <div className="review-layout">
        <div className="timeline-panel">
          <header><h2>面试过程</h2><span>{timeline.length} 条记录</span></header>
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
          {!loading && timeline.length === 0 ? <div className="table-empty-state"><strong>暂无面试内容</strong><span>面试中的问题和回答会显示在这里。</span></div> : null}
        </div>
        <aside className="audio-review-panel">
          <span className="side-panel-label">声音回放</span>
          <h2>面试录音</h2>
          <p>选择一方的声音进行回放。</p>
          <button className="audio-track" type="button"><Play size={18} weight="fill" /><span>面试官声音</span><b>播放</b></button>
          <button className="audio-track audio-track--candidate" type="button"><Play size={18} weight="fill" /><span>我的声音</span><b>播放</b></button>
          <hr />
          <h3>已经保存</h3>
          <dl>
            <div><dt>问题</dt><dd>面试官提出的问题</dd></div>
            <div><dt>对话</dt><dd>面试官和你的发言</dd></div>
            <div><dt>回答</dt><dd>当时显示的建议回答</dd></div>
          </dl>
          <div className="review-integrity"><CheckCircle size={18} weight="fill" /><span><strong>记录已保存</strong><small>你可以随时返回查看</small></span></div>
        </aside>
      </div>
    </section>
  )
}

function eventView(event: TaskEventRecord) {
  const payload = event.payload
  if (event.event_type === 'transcript.final') {
    return {
      type: payload.channel === 'candidate' ? '我' : '面试官',
      title: String(payload.text ?? ''),
      detail: '语音已记录',
    }
  }
  if (event.event_type === 'focus.updated') {
    return { type: '面试问题', title: String(payload.question ?? ''), detail: '问题已整理' }
  }
  if (event.event_type === 'answer.completed') {
    return { type: '建议回答', title: String(payload.answer ?? ''), detail: '回答已显示' }
  }
  if (event.event_type === 'answer.cancelled') {
    return { type: '回答更新', title: '已经切换到新的问题', detail: '旧回答已停止' }
  }
  return { type: '使用提醒', title: String(payload.message ?? '出现了一条提醒'), detail: '请稍后查看' }
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
