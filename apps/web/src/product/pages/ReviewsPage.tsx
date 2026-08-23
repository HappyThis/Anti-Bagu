import { ArrowRight, CheckCircle, Clock, FileText, MagnifyingGlass } from '@phosphor-icons/react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { apiRequest } from '../../shared/api'
import { useAuth } from '../AuthContext'
import { useProduct } from '../ProductContext'
import type { TaskStatus } from '../types'

interface ApiReview {
  id: string
  task_id: string
  task_name: string
  date: string
  duration_seconds: number
  question_count: number
  avg_latency_ms: number
}

const STATUS_LABEL: Record<TaskStatus, string> = {
  draft: '待开始',
  checking: '正在检查',
  check_failed: '需要检查',
  ready: '可以开始',
  running: '进行中',
  paused: '已暂停',
  completed: '已完成',
}

export function ReviewsPage() {
  const navigate = useNavigate()
  const { session } = useAuth()
  const { tasks, loading: tasksLoading } = useProduct()
  const [query, setQuery] = useState('')
  const [reviews, setReviews] = useState<ApiReview[]>([])
  const [reviewsLoading, setReviewsLoading] = useState(true)

  useEffect(() => {
    if (!session) return
    apiRequest<ApiReview[]>('/reviews', {}, session.token)
      .then(setReviews)
      .finally(() => setReviewsLoading(false))
  }, [session])

  const reviewByTask = useMemo(
    () => new Map(reviews.map((review) => [review.task_id, review])),
    [reviews],
  )
  const normalizedQuery = query.trim().toLowerCase()
  const visibleTasks = tasks.filter((task) => task.name.toLowerCase().includes(normalizedQuery))
  const completedCount = tasks.filter((task) => task.status === 'completed').length
  const totalQuestions = reviews.reduce((sum, review) => sum + review.question_count, 0)
  const loading = tasksLoading || reviewsLoading

  return (
    <section className="content-page">
      <span className="eyebrow">面试记录</span>
      <h1>所有面试</h1>
      <p className="page-lead">待开始、进行中和已完成的面试都保存在这里。</p>

      <div className="review-metrics">
        <span><small>全部面试</small><strong>{tasks.length}</strong><em>所有记录</em></span>
        <span><small>已完成</small><strong>{completedCount}</strong><em>可以复盘</em></span>
        <span><small>整理问题</small><strong>{totalQuestions}</strong><em>来自已完成面试</em></span>
      </div>

      <section className="review-list-card">
        <header className="list-toolbar">
          <div><strong>面试列表</strong><span>{tasks.length} 条记录</span></div>
          <label className="search-field"><MagnifyingGlass size={18} /><input aria-label="搜索面试" placeholder="搜索面试名称" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        </header>
        <div className="review-list">
          {visibleTasks.map((task) => {
            const review = reviewByTask.get(task.id)
            const duration = review ? `${Math.max(1, Math.round(review.duration_seconds / 60))} 分钟` : '尚未完成'
            return (
              <button className="review-row" key={task.id} type="button" onClick={() => navigate(`/reviews/${task.id}`)}>
                <span className="review-icon"><FileText size={22} /></span>
                <span className="review-primary">
                  <strong>{task.name}</strong>
                  <time>{task.createdAt}</time>
                </span>
                <span><Clock size={17} />{duration}</span>
                <span>{review ? `${review.question_count} 个问题` : '暂无问题'}</span>
                <span className={`record-status record-status--${task.status}`}><CheckCircle size={17} />{STATUS_LABEL[task.status]}</span>
                <ArrowRight size={19} />
              </button>
            )
          })}
          {visibleTasks.length === 0 ? <div className="table-empty-state"><MagnifyingGlass size={24} /><strong>{loading ? '正在加载面试记录…' : '没有找到面试'}</strong><span>{loading ? '请稍候' : '新建面试后会显示在这里'}</span></div> : null}
        </div>
        <footer className="list-footer"><span>显示 {visibleTasks.length} / {tasks.length} 条记录</span></footer>
      </section>
    </section>
  )
}
