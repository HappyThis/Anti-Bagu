import { Brain, Check, Eye, EyeSlash, ShieldCheck, Waveform } from '@phosphor-icons/react'
import { useEffect, useState, type FormEvent } from 'react'

import { apiRequest } from '../../shared/api'
import { useAuth } from '../AuthContext'

interface ServiceStatus {
  agent_connected: boolean
  asr: { name?: string; configured: boolean; latency_ms?: number }
  llm: { name?: string; configured: boolean; latency_ms?: number }
  storage?: string
}

export function DevicesPage() {
  const { session } = useAuth()
  const [services, setServices] = useState<ServiceStatus | null>(null)
  const [dashscopeKey, setDashscopeKey] = useState('')
  const [deepseekKey, setDeepseekKey] = useState('')
  const [showDashscope, setShowDashscope] = useState(false)
  const [showDeepseek, setShowDeepseek] = useState(false)
  const [savingKeys, setSavingKeys] = useState(false)
  const [keyMessage, setKeyMessage] = useState('')
  const [keyError, setKeyError] = useState('')

  useEffect(() => {
    if (!session) return
    let disposed = false
    apiRequest<ServiceStatus>('/model-status', {}, session.token)
      .then((status) => {
        if (!disposed) setServices(status)
      })
      .catch((requestError) => {
        if (!disposed) {
          setKeyError(requestError instanceof Error ? requestError.message : '暂时无法读取服务状态。')
        }
      })
    return () => {
      disposed = true
    }
  }, [session])

  const modelsReady = Boolean(services?.asr.configured && services?.llm.configured)

  async function saveCredentials(event: FormEvent) {
    event.preventDefault()
    if (!session) return
    if (!dashscopeKey.trim() && !deepseekKey.trim()) {
      setKeyError('请输入需要保存或更新的服务密钥。')
      return
    }
    setSavingKeys(true)
    setKeyError('')
    setKeyMessage('')
    try {
      const payload: Record<string, string> = {}
      if (dashscopeKey.trim()) payload.dashscope_api_key = dashscopeKey.trim()
      if (deepseekKey.trim()) payload.deepseek_api_key = deepseekKey.trim()
      const result = await apiRequest<Omit<ServiceStatus, 'agent_connected'>>('/model-credentials', {
        method: 'PUT',
        body: JSON.stringify(payload),
      }, session.token)
      setServices((current) => ({
        agent_connected: current?.agent_connected ?? false,
        ...result,
      }))
      setDashscopeKey('')
      setDeepseekKey('')
      setKeyMessage('两项服务已经连接，密钥已安全保存。')
    } catch (requestError) {
      setKeyError(requestError instanceof Error ? requestError.message : '保存失败，请稍后重试。')
    } finally {
      setSavingKeys(false)
    }
  }

  return (
    <section className="content-page simple-settings-page">
      <span className="eyebrow">设置</span>
      <h1>模型服务</h1>
      <p className="page-lead">管理语音识别和建议回答使用的服务密钥。</p>

      <form className="web-model-settings web-model-settings--standalone" onSubmit={saveCredentials}>
        <div className="settings-section-heading">
          <div>
            <span className="eyebrow">服务连接</span>
            <h2>配置模型服务</h2>
            <p>密钥由服务端加密保存，不会发送给电脑助手，也不会再次显示在页面中。</p>
          </div>
          <span className="encrypted-storage-badge"><ShieldCheck size={17} weight="fill" />{services?.storage ?? '服务器加密保存'}</span>
        </div>

        <div className="model-settings-grid">
          <section className="model-settings-block">
            <header>
              <span className="model-icon"><Waveform size={23} weight="duotone" /></span>
              <div><span className="model-kind">语音识别</span><h2>面试声音转文字</h2></div>
              <span className={`connected-pill ${services?.asr.configured ? '' : 'connected-pill--offline'}`}><i />{services?.asr.configured ? '已保存' : '待设置'}</span>
            </header>
            <label>
              <span>语音识别服务密钥</span>
              <div className="secret-input">
                <input autoComplete="off" type={showDashscope ? 'text' : 'password'} value={dashscopeKey} placeholder={services?.asr.configured ? '已保存，输入新密钥可替换' : '粘贴 DashScope 服务密钥'} onChange={(event) => setDashscopeKey(event.target.value)} />
                <button type="button" aria-label={showDashscope ? '隐藏密钥' : '显示密钥'} onClick={() => setShowDashscope((current) => !current)}>{showDashscope ? <EyeSlash size={18} /> : <Eye size={18} />}</button>
              </div>
            </label>
            <small>用于把面试声音转换成文字。</small>
          </section>

          <section className="model-settings-block">
            <header>
              <span className="model-icon"><Brain size={23} weight="duotone" /></span>
              <div><span className="model-kind">回答生成</span><h2>问题识别与建议回答</h2></div>
              <span className={`connected-pill ${services?.llm.configured ? '' : 'connected-pill--offline'}`}><i />{services?.llm.configured ? '已保存' : '待设置'}</span>
            </header>
            <label>
              <span>回答服务密钥</span>
              <div className="secret-input">
                <input autoComplete="off" type={showDeepseek ? 'text' : 'password'} value={deepseekKey} placeholder={services?.llm.configured ? '已保存，输入新密钥可替换' : '粘贴 DeepSeek 服务密钥'} onChange={(event) => setDeepseekKey(event.target.value)} />
                <button type="button" aria-label={showDeepseek ? '隐藏密钥' : '显示密钥'} onClick={() => setShowDeepseek((current) => !current)}>{showDeepseek ? <EyeSlash size={18} /> : <Eye size={18} />}</button>
              </div>
            </label>
            <small>用于识别当前问题并生成建议回答。</small>
          </section>
        </div>

        {keyMessage ? <div className="inline-success" role="status"><Check size={18} weight="bold" />{keyMessage}</div> : null}
        {keyError ? <div className="form-error model-key-error" role="alert">{keyError}</div> : null}
        <div className="sticky-save-row">
          <span>{modelsReady ? '更新其中一项时，另一项留空即可保留原值。' : '首次设置需要完整填写两项服务密钥。'}</span>
          <button className="primary-action save-model-button" type="submit" disabled={savingKeys}>{savingKeys ? '正在检查连接…' : '保存并检查连接'}</button>
        </div>
      </form>
    </section>
  )
}
