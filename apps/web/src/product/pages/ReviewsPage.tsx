import { ArrowRight, Clock, FileText, FunnelSimple, Gauge, MagnifyingGlass } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { apiRequest } from '../../shared/api'
import { useAuth } from '../AuthContext'
import type { ReviewRecord } from '../types'

interface ApiReview {
  id: string
  task_id: string
  task_name: string
  date: string
  duration_seconds: number
  question_count: number
  avg_latency_ms: number
}

export function ReviewsPage() {
  const navigate = useNavigate()
  const { session } = useAuth()
  const [query, setQuery] = useState('')
  const [reviews, setReviews] = useState<ReviewRecord[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!session) return
    apiRequest<ApiReview[]>('/reviews', {}, session.token)
      .then((rows) => setReviews(rows.map((row) => ({
        id: row.id,
        taskId: row.task_id,
        taskName: row.task_name,
        date: new Date(row.date).toLocaleString('zh-CN', { hour12: false }),
        duration: `${Math.max(1, Math.round(row.duration_seconds / 60))} 分钟`,
        questionCount: row.question_count,
        avgLatency: Math.round(row.avg_latency_ms),
      }))))
      .finally(() => setLoading(false))
  }, [session])

  const visibleReviews = reviews.filter((review) => review.taskName.toLowerCase().includes(query.trim().toLowerCase()))
  const totalQuestions = reviews.reduce((sum, review) => sum + review.questionCount, 0)
  const averageLatency = reviews.length
    ? Math.round(reviews.reduce((sum, review) => sum + review.avgLatency, 0) / reviews.length)
    : 0
  return (
    <section className="content-page">
      <span className="eyebrow">面试复盘</span>
      <h1>回看每一次 Focus 如何变化</h1>
      <p className="page-lead">原始双路对话、模型输入、回答、延迟和系统事件都保留在同一条时间线上。</p>

      <div className="review-metrics">
        <span><small>已完成任务</small><strong>{reviews.length}</strong><em>全部记录</em></span>
        <span><small>累计问题</small><strong>{totalQuestions}</strong><em>Focus 识别</em></span>
        <span><small>平均延迟</small><strong>{averageLatency ? `${(averageLatency / 1000).toFixed(1)} s` : '—'}</strong><em>端到端</em></span>
      </div>

      <section className="review-list-card">
        <header className="list-toolbar">
          <div><strong>历史任务</strong><span>{reviews.length} 条记录</span></div>
          <div className="toolbar-actions">
            <label className="search-field"><MagnifyingGlass size={18} /><input aria-label="搜索复盘" placeholder="搜索任务名称" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
            <button className="secondary-action compact-action" type="button"><FunnelSimple size={18} />筛选</button>
          </div>
        </header>
        <div className="review-list">
        {visibleReviews.map((review) => (
          <button className="review-row" key={review.id} type="button" onClick={() => navigate(`/reviews/${review.id}`)}>
            <span className="review-icon"><FileText size={22} /></span>
            <span className="review-primary">
              <strong>{review.taskName}</strong>
              <time>{review.date}</time>
            </span>
            <span><Clock size={17} />{review.duration}</span>
            <span>{review.questionCount} 个问题</span>
            <span><Gauge size={17} />平均 {review.avgLatency} ms</span>
            <ArrowRight size={19} />
          </button>
        ))}
        {visibleReviews.length === 0 ? <div className="table-empty-state"><MagnifyingGlass size={24} /><strong>{loading ? '正在加载复盘…' : '没有匹配的任务'}</strong><span>{loading ? '请稍候' : '完成的面试任务会显示在这里'}</span></div> : null}
        </div>
        <footer className="list-footer"><span>显示 {visibleReviews.length} / {reviews.length} 条记录</span><button type="button">查看归档</button></footer>
      </section>
    </section>
  )
}
