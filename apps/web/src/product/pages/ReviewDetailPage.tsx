import { ArrowLeft, CheckCircle, DownloadSimple } from '@phosphor-icons/react'
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

interface ReviewFocusCard {
  id: string
  question: string
  answer: string
  code: string
  source: string
  createdAt: string
}

const DISPLAYED_EVENTS = new Set([
  'transcript.final',
  'focus.updated',
  'answer.completed',
  'answer.cancelled',
  'error',
])
const REVIEW_EVENT_TYPES = [...DISPLAYED_EVENTS].join(',')

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
    apiRequest<TaskEventRecord[]>(`/tasks/${reviewId}/events?limit=5000&types=${encodeURIComponent(REVIEW_EVENT_TYPES)}`, {}, session.token)
      .then(setEvents)
      .finally(() => setLoading(false))
  }, [reviewId, session])

  const timeline = useMemo(
    () => events.filter((event) => DISPLAYED_EVENTS.has(event.event_type)),
    [events],
  )
  const focusCards = useMemo(() => buildFocusCards(events), [events])
  const focuses = new Set(events.filter((event) => event.event_type === 'focus.updated').map((event) => String(event.payload.focus_id ?? event.event_id)))
  const answers = new Set(events.filter((event) => event.event_type === 'answer.completed').map((event) => String(event.payload.focus_id ?? event.event_id)))
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
        <span><small>面试问题</small><strong>{focuses.size}</strong><em>自动整理</em></span>
        <span><small>建议回答</small><strong>{answers.size}</strong><em>已保存</em></span>
        <span><small>回答切换</small><strong>{interrupted.length}</strong><em>遇到新问题</em></span>
        <span><small>记录状态</small><strong>{events.length ? '已保存' : '—'}</strong><em><CheckCircle size={13} weight="fill" />可以查看</em></span>
      </div>

      <section className="review-focus-section">
        <header><div><span className="eyebrow">问题复盘</span><h2>问题与建议回答</h2></div><span>{focusCards.length} 个问题</span></header>
        <div className="review-focus-list">
          {focusCards.map((focus, index) => (
            <article className="review-focus-card" key={focus.id}>
              <header><span>问题 {index + 1}</span><time>{new Date(focus.createdAt).toLocaleTimeString('zh-CN', { hour12: false })}</time>{focus.source === 'SCREENSHOT' ? <em>截图识别</em> : null}</header>
              <h3>{focus.question}</h3>
              <div><span>建议回答</span><p>{focus.answer || '本题没有保存建议回答。'}</p></div>
              {focus.code ? <details><summary>查看 Python 代码</summary><pre><code>{focus.code}</code></pre></details> : null}
            </article>
          ))}
          {!loading && focusCards.length === 0 ? <div className="table-empty-state"><strong>暂无面试问题</strong><span>识别到的问题和建议回答会显示在这里。</span></div> : null}
        </div>
      </section>

      <details className="review-raw-details">
        <summary>查看完整对话与系统记录（{timeline.length} 条）</summary>
        <div className="timeline-panel">
          <header><h2>完整时间线</h2><span>{timeline.length} 条记录</span></header>
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
        </div>
      </details>
    </section>
  )
}

function buildFocusCards(events: TaskEventRecord[]): ReviewFocusCard[] {
  const cards = new Map<string, ReviewFocusCard>()
  for (const event of events) {
    if (event.event_type !== 'focus.updated' && event.event_type !== 'answer.completed') continue
    const id = String(event.payload.focus_id ?? event.event_id)
    const current = cards.get(id) ?? {
      id,
      question: '',
      answer: '',
      code: '',
      source: 'VOICE',
      createdAt: event.created_at,
    }
    current.question = String(event.payload.question ?? current.question)
    current.source = String(event.payload.source ?? current.source)
    if (event.event_type === 'answer.completed') {
      current.answer = String(event.payload.answer ?? '')
      current.code = String(event.payload.code ?? '')
    }
    cards.set(id, current)
  }
  return [...cards.values()].filter((card) => card.question)
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
