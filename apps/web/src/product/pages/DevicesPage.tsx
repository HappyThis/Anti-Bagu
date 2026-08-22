import {
  ArrowClockwise,
  Check,
  Desktop,
  DownloadSimple,
  Headphones,
  ShieldCheck,
} from '@phosphor-icons/react'
import { useCallback, useEffect, useState } from 'react'

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
  asr: { configured: boolean }
  llm: { configured: boolean }
}

export function DevicesPage() {
  const { session } = useAuth()
  const [testing, setTesting] = useState(false)
  const [devices, setDevices] = useState<DeviceRecord[]>([])
  const [services, setServices] = useState<ServiceStatus | null>(null)

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
            <li><b>3</b><span><strong>跟随提示完成设置</strong><small>登录账号并完成一次服务授权，以后无需重复。</small></span></li>
          </ol>
          <p className="settings-help-note">如果 macOS 提示“无法验证”，请打开“系统设置 → 隐私与安全性”，点击“仍要打开”。完成后保持电脑助手窗口打开，再回到面试准备页继续。</p>
        </section>

        <section className="readiness-summary">
          <h2>当前状态</h2>
          <div><Desktop size={23} /><span><strong>电脑助手</strong><small>{online ? '已经打开' : '等待打开'}</small></span><em className={online ? 'is-ready' : ''}>{online ? <Check size={17} weight="bold" /> : '—'}</em></div>
          <div><Headphones size={23} /><span><strong>面试声音</strong><small>{online ? '开始面试前会再次确认' : '连接后自动确认'}</small></span><em className={online ? 'is-ready' : ''}>{online ? <Check size={17} weight="bold" /> : '—'}</em></div>
          <div><ShieldCheck size={23} /><span><strong>回答功能</strong><small>{answersReady ? '已经准备好' : '请在电脑助手中完成设置'}</small></span><em className={answersReady ? 'is-ready' : ''}>{answersReady ? <Check size={17} weight="bold" /> : '—'}</em></div>
        </section>
      </div>

      <p className="privacy-note"><ShieldCheck size={18} weight="fill" />只有你开始面试后才会听取声音，结束后立即停止。</p>
    </section>
  )
}
