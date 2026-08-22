import { ArrowLeft, CheckCircle, DeviceMobile, Plus, ShieldCheck, Waveform } from '@phosphor-icons/react'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { useProduct } from '../ProductContext'

export function CreateTaskPage() {
  const navigate = useNavigate()
  const { createTask } = useProduct()
  const [name, setName] = useState('')
  const [mode, setMode] = useState<'interview' | 'practice'>('interview')
  const [mobileRequired, setMobileRequired] = useState(false)
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
      setError(requestError instanceof Error ? requestError.message : '面试创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="form-page">
      <button className="back-link" type="button" onClick={() => navigate('/tasks')}>
        <ArrowLeft size={18} />返回面试
      </button>
      <span className="eyebrow">新建面试</span>
      <h1>准备一场新的面试</h1>
      <p className="page-lead">填写一个容易辨认的名称，下一步会带你完成准备。</p>

      <div className="create-task-layout">
        <form className="task-form task-form-card" onSubmit={submit}>
          <div className="form-section-heading">
            <span>01</span>
            <div><strong>面试信息</strong><small>创建后仍可修改</small></div>
          </div>
          <label>
            <span>面试名称</span>
            <input
              autoFocus
              placeholder="例如：字节跳动后端二面"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <small>建议填写公司、岗位和轮次，例如“字节跳动后端二面”。</small>
          </label>

          <fieldset>
            <legend>这是一场什么面试？</legend>
            <div className="choice-row">
              <button
                className={mode === 'interview' ? 'choice-button choice-button--selected' : 'choice-button'}
                type="button"
                onClick={() => setMode('interview')}
              >
                <strong>正式面试</strong>
                <span>开始后显示问题和建议回答，并保存面试记录</span>
              </button>
              <button
                className={mode === 'practice' ? 'choice-button choice-button--selected' : 'choice-button'}
                type="button"
                onClick={() => setMode('practice')}
              >
                <strong>模拟练习</strong>
                <span>适合提前熟悉流程和检查电脑是否准备好</span>
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
              <strong>在手机上查看回答</strong>
              <small>开启后，开始面试前需要先连接手机。</small>
            </span>
          </label>

          <div className="form-actions">
            {error ? <span className="form-error form-error--inline" role="alert">{error}</span> : null}
            <button className="secondary-action" type="button" onClick={() => navigate('/tasks')}>取消</button>
            <button className="primary-action" type="submit" disabled={!name.trim() || submitting}>
              <Plus size={20} />{submitting ? '正在创建…' : '创建面试'}
            </button>
          </div>
        </form>

        <aside className="creation-guide">
          <span className="creation-guide-icon"><ShieldCheck size={24} weight="duotone" /></span>
          <h2>接下来怎么做？</h2>
          <p>创建后不会立即开始。完成三步准备，再由你亲自点击开始。</p>
          <ol>
            <li><CheckCircle size={19} weight="fill" /><span><strong>打开电脑助手</strong><small>打开后会自动连接</small></span></li>
            <li><Waveform size={19} weight="fill" /><span><strong>确认可以听清</strong><small>确保面试声音和你的声音正常</small></span></li>
            <li><DeviceMobile size={19} weight="fill" /><span><strong>开始面试</strong><small>一切准备好后由你点击开始</small></span></li>
          </ol>
        </aside>
      </div>
    </section>
  )
}
