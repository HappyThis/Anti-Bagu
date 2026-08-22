import { ArrowRight, CheckCircle, Clock, FileText, FunnelSimple, MagnifyingGlass } from '@phosphor-icons/react'
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
  return (
    <section className="content-page">
      <span className="eyebrow">面试记录</span>
      <h1>回顾每一场面试</h1>
      <p className="page-lead">查看面试官的问题、你当时的回答和页面给出的建议。</p>

      <div className="review-metrics">
        <span><small>已完成面试</small><strong>{reviews.length}</strong><em>全部记录</em></span>
        <span><small>面试问题</small><strong>{totalQuestions}</strong><em>自动整理</em></span>
        <span><small>记录状态</small><strong>{reviews.length ? '已保存' : '—'}</strong><em>可随时查看</em></span>
      </div>

      <section className="review-list-card">
        <header className="list-toolbar">
          <div><strong>历史面试</strong><span>{reviews.length} 条记录</span></div>
          <div className="toolbar-actions">
            <label className="search-field"><MagnifyingGlass size={18} /><input aria-label="搜索面试" placeholder="搜索面试名称" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
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
            <span><CheckCircle size={17} />记录已保存</span>
            <ArrowRight size={19} />
          </button>
        ))}
        {visibleReviews.length === 0 ? <div className="table-empty-state"><MagnifyingGlass size={24} /><strong>{loading ? '正在加载面试记录…' : '还没有完成的面试'}</strong><span>{loading ? '请稍候' : '面试结束后会自动保存在这里'}</span></div> : null}
        </div>
        <footer className="list-footer"><span>显示 {visibleReviews.length} / {reviews.length} 条记录</span><button type="button">查看归档</button></footer>
      </section>
    </section>
  )
}
