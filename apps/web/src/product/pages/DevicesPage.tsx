import {
  ArrowClockwise,
  Brain,
  Check,
  Desktop,
  DownloadSimple,
  Eye,
  EyeSlash,
  Headphones,
  ShieldCheck,
  Waveform,
} from '@phosphor-icons/react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { apiRequest } from '../../shared/api'
import { useAuth } from '../AuthContext'

interface DeviceRecord {
  id: string
  name: string
  status: 'online' | 'offline'
  last_seen_at: string
}

interface ServiceStatus {
  agent_connected: boolean
  asr: { name?: string; configured: boolean; latency_ms?: number }
  llm: { name?: string; configured: boolean; latency_ms?: number }
  storage?: string
}

export function DevicesPage() {
  const { session } = useAuth()
  const [testing, setTesting] = useState(false)
  const [devices, setDevices] = useState<DeviceRecord[]>([])
  const [services, setServices] = useState<ServiceStatus | null>(null)
  const [dashscopeKey, setDashscopeKey] = useState('')
  const [deepseekKey, setDeepseekKey] = useState('')
  const [showDashscope, setShowDashscope] = useState(false)
  const [showDeepseek, setShowDeepseek] = useState(false)
  const [savingKeys, setSavingKeys] = useState(false)
  const [keyMessage, setKeyMessage] = useState('')
  const [keyError, setKeyError] = useState('')

  const refresh = useCallback(async () => {
    if (!session) return
    setTesting(true)
    try {
      const [deviceRows, serviceStatus] = await Promise.all([
        apiRequest<DeviceRecord[]>('/devices', {}, session.token),
        apiRequest<ServiceStatus>('/model-status', {}, session.token),
      ])
      setDevices(deviceRows)
      setServices(serviceStatus)
    } finally {
      setTesting(false)
    }
  }, [session])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const device = devices[0]
  const online = device?.status === 'online'
  const answersReady = Boolean(services?.asr.configured && services?.llm.configured)

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
      <h1>电脑助手</h1>
      <p className="page-lead">面试开始后，电脑助手负责听取声音并把建议回答发送到页面。</p>

      <section className={`helper-status-hero ${online ? 'helper-status-hero--online' : ''}`}>
        <span className="helper-hero-icon"><Desktop size={34} weight="duotone" /></span>
        <div>
          <span>{online ? '已经连接' : '首次使用'}</span>
          <h2>{online ? `${device?.name ?? '这台电脑'}已准备好` : '先下载并打开电脑助手'}</h2>
          <p>{online ? '面试开始前，页面还会带你确认一次声音。' : '下载后按照提示登录账号，打开时会自动连接。'}</p>
        </div>
        {online ? <button className="secondary-action" type="button" onClick={() => void refresh()} disabled={testing}><ArrowClockwise className={testing ? 'spin' : ''} size={18} />重新确认</button> : <a className="primary-action" href="/downloads/anti-bagu-agent-macos-arm64.tar.gz" download><DownloadSimple size={19} />下载电脑助手</a>}
      </section>

      <div className="simple-setup-layout">
        <section className="simple-setup-steps">
          <h2>第一次使用</h2>
          <ol>
            <li><b>1</b><span><strong>下载并解压</strong><small>双击下载的文件，电脑会自动解压。</small></span></li>
            <li><b>2</b><span><strong>双击“开始使用.command”</strong><small>如果被 macOS 拦截，按住 Control 点击文件并选择“打开”。</small></span></li>
            <li><b>3</b><span><strong>允许声音权限</strong><small>电脑助手会打开对应的系统设置页，按提示打开权限后重新启动。</small></span></li>
          </ol>
          <p className="settings-help-note">系统音频没有权限时，请在“屏幕与系统音频录制”列表中打开“终端（Terminal）”或“anti-bagu-agent”，然后完全退出电脑助手并重新打开。</p>
          <p className="settings-help-note">如果 macOS 提示“无法验证”，请打开“系统设置 → 隐私与安全性”，点击“仍要打开”。</p>
        </section>

        <section className="readiness-summary">
          <h2>当前状态</h2>
          <div><Desktop size={23} /><span><strong>电脑助手</strong><small>{online ? '已经打开' : '等待打开'}</small></span><em className={online ? 'is-ready' : ''}>{online ? <Check size={17} weight="bold" /> : '—'}</em></div>
          <div><Headphones size={23} /><span><strong>面试声音</strong><small>{online ? '开始面试前会再次确认' : '连接后自动确认'}</small></span><em className={online ? 'is-ready' : ''}>{online ? <Check size={17} weight="bold" /> : '—'}</em></div>
          <div><ShieldCheck size={23} /><span><strong>回答功能</strong><small>{answersReady ? '已经准备好' : '请在下方保存两项服务密钥'}</small></span><em className={answersReady ? 'is-ready' : ''}>{answersReady ? <Check size={17} weight="bold" /> : '—'}</em></div>
        </section>
      </div>

      <form className="web-model-settings" onSubmit={saveCredentials}>
        <div className="settings-section-heading">
          <div>
            <span className="eyebrow">回答服务</span>
            <h2>在网页中完成服务设置</h2>
            <p>密钥只会发送到 Anti-Bagu 服务端并加密保存，不会交给电脑助手，也不会再次显示在页面中。</p>
          </div>
          <span className="encrypted-storage-badge"><ShieldCheck size={17} weight="fill" />{services?.storage ?? '服务器加密保存'}</span>
        </div>

        <div className="model-settings-grid">
          <section className="model-settings-block">
            <header>
              <span className="model-icon"><Waveform size={23} weight="duotone" /></span>
              <div><span className="model-kind">语音识别</span><h2>{services?.asr.name ?? 'Qwen Audio ASR Flash'}</h2></div>
              <span className={`connected-pill ${services?.asr.configured ? '' : 'connected-pill--offline'}`}><i />{services?.asr.configured ? '已保存' : '待设置'}</span>
            </header>
            <label>
              <span>语音识别服务密钥</span>
              <div className="secret-input">
                <input
                  autoComplete="off"
                  type={showDashscope ? 'text' : 'password'}
                  value={dashscopeKey}
                  placeholder={services?.asr.configured ? '已保存，输入新密钥可替换' : '粘贴 DashScope 服务密钥'}
                  onChange={(event) => setDashscopeKey(event.target.value)}
                />
                <button type="button" aria-label={showDashscope ? '隐藏密钥' : '显示密钥'} onClick={() => setShowDashscope((current) => !current)}>{showDashscope ? <EyeSlash size={18} /> : <Eye size={18} />}</button>
              </div>
            </label>
            <small>用于把面试声音转换成文字。</small>
          </section>

          <section className="model-settings-block">
            <header>
              <span className="model-icon"><Brain size={23} weight="duotone" /></span>
              <div><span className="model-kind">回答生成</span><h2>{services?.llm.name ?? 'DeepSeek V4 Flash Vision'}</h2></div>
              <span className={`connected-pill ${services?.llm.configured ? '' : 'connected-pill--offline'}`}><i />{services?.llm.configured ? '已保存' : '待设置'}</span>
            </header>
            <label>
              <span>回答服务密钥</span>
              <div className="secret-input">
                <input
                  autoComplete="off"
                  type={showDeepseek ? 'text' : 'password'}
                  value={deepseekKey}
                  placeholder={services?.llm.configured ? '已保存，输入新密钥可替换' : '粘贴 DeepSeek 服务密钥'}
                  onChange={(event) => setDeepseekKey(event.target.value)}
                />
                <button type="button" aria-label={showDeepseek ? '隐藏密钥' : '显示密钥'} onClick={() => setShowDeepseek((current) => !current)}>{showDeepseek ? <EyeSlash size={18} /> : <Eye size={18} />}</button>
              </div>
            </label>
            <small>用于识别当前问题并生成建议回答。</small>
          </section>
        </div>

        {keyMessage ? <div className="inline-success" role="status"><Check size={18} weight="bold" />{keyMessage}</div> : null}
        {keyError ? <div className="form-error model-key-error" role="alert">{keyError}</div> : null}
        <div className="sticky-save-row">
          <span>{answersReady ? '更新其中一项时，另一项留空即可保留原值。' : '首次设置需要完整填写两项服务密钥。'}</span>
          <button className="primary-action save-model-button" type="submit" disabled={savingKeys}>{savingKeys ? '正在检查连接…' : '保存并检查连接'}</button>
        </div>
      </form>

      <p className="privacy-note"><ShieldCheck size={18} weight="fill" />只有你开始面试后才会听取声音，结束后立即停止。</p>
    </section>
  )
}
