import { ArrowRight, CheckCircle, Clock, FileText, MagnifyingGlass, PencilSimple, Trash } from '@phosphor-icons/react'
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
  const { tasks, loading: tasksLoading, renameTask, deleteTask } = useProduct()
  const [query, setQuery] = useState('')
  const [reviews, setReviews] = useState<ApiReview[]>([])
  const [reviewsLoading, setReviewsLoading] = useState(true)
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null)
  const [deletingTaskId, setDeletingTaskId] = useState<string | null>(null)
  const [draftName, setDraftName] = useState('')
  const [saving, setSaving] = useState(false)
  const [actionError, setActionError] = useState('')

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
  const taskIDs = new Set(tasks.map((task) => task.id))
  const totalQuestions = reviews.reduce((sum, review) => sum + (taskIDs.has(review.task_id) ? review.question_count : 0), 0)
  const loading = tasksLoading || reviewsLoading
  const editingTask = tasks.find((task) => task.id === editingTaskId)
  const deletingTask = tasks.find((task) => task.id === deletingTaskId)

  async function saveName() {
    if (!editingTask || !draftName.trim()) return
    setSaving(true)
    setActionError('')
    try {
      await renameTask(editingTask.id, draftName.trim())
      setEditingTaskId(null)
    } catch (requestError) {
      setActionError(requestError instanceof Error ? requestError.message : '修改失败')
    } finally {
      setSaving(false)
    }
  }

  async function confirmDelete() {
    if (!deletingTask) return
    setSaving(true)
    setActionError('')
    try {
      await deleteTask(deletingTask.id)
      setDeletingTaskId(null)
    } catch (requestError) {
      setActionError(requestError instanceof Error ? requestError.message : '删除失败')
    } finally {
      setSaving(false)
    }
  }

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
              <div className="review-row" key={task.id}>
                <span className="review-icon"><FileText size={22} /></span>
                <button className="review-primary review-primary-button" type="button" onClick={() => navigate(`/reviews/${task.id}`)}>
                  <strong>{task.name}</strong>
                  <time>{task.createdAt}</time>
                </button>
                <span><Clock size={17} />{duration}</span>
                <span>{review ? `${review.question_count} 个问题` : '暂无问题'}</span>
                <span className={`record-status record-status--${task.status}`}><CheckCircle size={17} />{STATUS_LABEL[task.status]}</span>
                <button className="review-open-button" type="button" aria-label={`查看 ${task.name}`} onClick={() => navigate(`/reviews/${task.id}`)}><ArrowRight size={19} /></button>
                <div className="review-row-actions"><button type="button" aria-label={`修改 ${task.name}`} onClick={() => { setEditingTaskId(task.id); setDraftName(task.name); setActionError('') }}><PencilSimple size={17} /></button><button type="button" aria-label={`删除 ${task.name}`} disabled={task.status === 'running' || task.status === 'paused'} onClick={() => { setDeletingTaskId(task.id); setActionError('') }}><Trash size={17} /></button></div>
              </div>
            )
          })}
          {visibleTasks.length === 0 ? <div className="table-empty-state"><MagnifyingGlass size={24} /><strong>{loading ? '正在加载面试记录…' : '没有找到面试'}</strong><span>{loading ? '请稍候' : '新建面试后会显示在这里'}</span></div> : null}
        </div>
        <footer className="list-footer"><span>显示 {visibleTasks.length} / {tasks.length} 条记录</span></footer>
      </section>
      {editingTask ? <div className="dialog-backdrop" role="presentation"><section className="record-action-dialog" role="dialog" aria-modal="true" aria-labelledby="rename-record-title"><span className="eyebrow">面试记录</span><h2 id="rename-record-title">修改面试名称</h2><p>新的名称会同步显示在面试记录和复盘页面。</p><label><span>面试名称</span><input autoFocus value={draftName} onChange={(event) => setDraftName(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void saveName(); if (event.key === 'Escape') setEditingTaskId(null) }} /></label>{actionError ? <div className="form-error" role="alert">{actionError}</div> : null}<div className="dialog-actions"><button className="secondary-action" type="button" onClick={() => setEditingTaskId(null)}>取消</button><button className="primary-action" type="button" disabled={!draftName.trim() || saving} onClick={() => void saveName()}>{saving ? '正在保存…' : '保存名称'}</button></div></section></div> : null}
      {deletingTask ? <div className="dialog-backdrop" role="presentation"><section className="record-action-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-record-title"><span className="eyebrow eyebrow--danger">删除记录</span><h2 id="delete-record-title">确定删除“{deletingTask.name}”吗？</h2><p>删除后你将看不到这条记录，但管理员仍可恢复，所有面试数据都会保留。</p>{actionError ? <div className="form-error" role="alert">{actionError}</div> : null}<div className="dialog-actions"><button className="secondary-action" type="button" onClick={() => setDeletingTaskId(null)}>取消</button><button className="danger-action" type="button" disabled={saving} onClick={() => void confirmDelete()}>{saving ? '正在删除…' : '删除记录'}</button></div></section></div> : null}
    </section>
  )
}
