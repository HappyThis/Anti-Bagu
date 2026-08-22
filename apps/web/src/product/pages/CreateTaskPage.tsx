import { ArrowLeft, CheckCircle, DeviceMobile, Plus, ShieldCheck, Waveform } from '@phosphor-icons/react'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { useProduct } from '../ProductContext'

export function CreateTaskPage() {
  const navigate = useNavigate()
  const { createTask } = useProduct()
  const [name, setName] = useState('')
  const [mode, setMode] = useState<'interview' | 'practice'>('interview')
  const [mobileRequired, setMobileRequired] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent) {
    event.preventDefault()
    const taskName = name.trim()
    if (!taskName) return
    setSubmitting(true)
    setError('')
    try {
      const id = await createTask(taskName, mode, mobileRequired)
      navigate(`/tasks/${id}`)
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '任务创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="form-page">
      <button className="back-link" type="button" onClick={() => navigate('/tasks')}>
        <ArrowLeft size={18} />返回任务
      </button>
      <span className="eyebrow">新建任务</span>
      <h1>准备一场新的面试</h1>
      <p className="page-lead">任务名称完全由你定义，创建后会进入系统检查。</p>

      <div className="create-task-layout">
        <form className="task-form task-form-card" onSubmit={submit}>
          <div className="form-section-heading">
            <span>01</span>
            <div><strong>任务基本信息</strong><small>任务创建后仍可修改名称</small></div>
          </div>
          <label>
            <span>任务名称</span>
            <input
              autoFocus
              placeholder="例如：字节跳动后端二面"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <small>建议使用公司、岗位或面试轮次，方便后续复盘。</small>
          </label>

          <fieldset>
            <legend>任务模式</legend>
            <div className="choice-row">
              <button
                className={mode === 'interview' ? 'choice-button choice-button--selected' : 'choice-button'}
                type="button"
                onClick={() => setMode('interview')}
              >
                <strong>正式面试</strong>
                <span>双路采集、实时回答并保存完整数据</span>
              </button>
              <button
                className={mode === 'practice' ? 'choice-button choice-button--selected' : 'choice-button'}
                type="button"
                onClick={() => setMode('practice')}
              >
                <strong>模拟练习</strong>
                <span>用于自测和验证设备、模型效果</span>
              </button>
            </div>
          </fieldset>

          <label className="switch-label">
            <input
              checked={mobileRequired}
              type="checkbox"
              onChange={(event) => setMobileRequired(event.target.checked)}
            />
            <span>
              <strong>要求手机端配对</strong>
              <small>系统检查时，手机必须在线并确认收到测试消息。</small>
            </span>
          </label>

          <div className="form-actions">
            {error ? <span className="form-error form-error--inline" role="alert">{error}</span> : null}
            <button className="secondary-action" type="button" onClick={() => navigate('/tasks')}>取消</button>
            <button className="primary-action" type="submit" disabled={!name.trim() || submitting}>
              <Plus size={20} />{submitting ? '正在创建…' : '创建任务'}
            </button>
          </div>
        </form>

        <aside className="creation-guide">
          <span className="creation-guide-icon"><ShieldCheck size={24} weight="duotone" /></span>
          <h2>创建后会做什么？</h2>
          <p>任务不会立即开始采集。系统会先检查整条链路，全部通过后由你手动开始。</p>
          <ol>
            <li><CheckCircle size={19} weight="fill" /><span><strong>连接桌面 Agent</strong><small>确认采集端在线</small></span></li>
            <li><Waveform size={19} weight="fill" /><span><strong>测试双路音频与模型</strong><small>展示真实连接延迟</small></span></li>
            <li><DeviceMobile size={19} weight="fill" /><span><strong>配对手机端</strong><small>验证建议回答可送达</small></span></li>
          </ol>
        </aside>
      </div>
    </section>
  )
}
