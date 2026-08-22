import { ArrowClockwise, CheckCircle, Copy, Desktop, DownloadSimple, Keyboard, Microphone, ShieldCheck, SpeakerHigh } from '@phosphor-icons/react'
import { useCallback, useEffect, useState } from 'react'

import { apiRequest } from '../../shared/api'
import { useAuth } from '../AuthContext'

interface DeviceRecord {
  id: string
  name: string
  platform: string
  agent_version: string
  status: 'online' | 'offline'
  last_seen_at: string
  metadata: Record<string, unknown>
}

export function DevicesPage() {
  const { session } = useAuth()
  const [testing, setTesting] = useState(false)
  const [devices, setDevices] = useState<DeviceRecord[]>([])

  const loadDevices = useCallback(async () => {
    if (!session) return
    const rows = await apiRequest<DeviceRecord[]>('/devices', {}, session.token)
    setDevices(rows)
  }, [session])

  useEffect(() => {
    void loadDevices()
  }, [loadDevices])

  async function testDevices() {
    setTesting(true)
    try {
      await loadDevices()
    } finally {
      setTesting(false)
    }
  }

  const device = devices[0]
  const online = device?.status === 'online'

  return (
    <section className="content-page">
      <span className="eyebrow">监听设备</span>
      <h1>桌面 Agent 与音频设备</h1>
      <p className="page-lead">任务开始前会再次执行完整检查，这里用于管理默认设备和权限。</p>

      <div className="device-overview-grid">
        <section className="device-hero">
          <span className="device-icon"><Desktop size={30} weight="duotone" /></span>
          <div><strong>{device?.name ?? '尚未连接桌面 Agent'}</strong><span>{device ? `${device.platform} · Agent ${device.agent_version}` : '请先在电脑终端登录并启动 CLI'}</span></div>
          <span className={`connected-pill ${online ? '' : 'connected-pill--offline'}`}><i />{online ? '在线' : '离线'}</span>
          <button className="secondary-action" type="button" onClick={testDevices} disabled={testing}>
            <ArrowClockwise className={testing ? 'spin' : ''} size={19} />{testing ? '检测中' : '重新检测'}
          </button>
          <div className="device-facts">
            <span><small>最后心跳</small><strong>{device ? new Date(device.last_seen_at).toLocaleTimeString('zh-CN', { hour12: false }) : '—'}</strong></span>
            <span><small>云端延迟</small><strong>{online ? '连接正常' : '—'}</strong></span>
            <span><small>当前任务</small><strong>未占用</strong></span>
          </div>
        </section>

        <aside className="agent-command-card">
          <span className="side-panel-label">桌面 CLI</span>
          <h2>启动采集端</h2>
          <p>首次使用先下载 macOS Agent；完成登录后，在终端运行：</p>
          <a className="agent-download-link" href="/downloads/anti-bagu-agent-macos-arm64.tar.gz" download><DownloadSimple size={17} />下载 macOS Agent</a>
          <code>anti-bagu-agent start</code>
          <button type="button" onClick={() => navigator.clipboard.writeText('anti-bagu-agent start')}><Copy size={17} />复制命令</button>
        </aside>
      </div>

      <div className="settings-section">
        <h2>默认音频设备</h2>
        <div className="settings-row">
          <SpeakerHigh size={25} />
          <div><strong>系统音频</strong><span>ScreenCaptureKit · 16kHz 单声道</span></div>
          <CheckCircle className={online ? 'success-icon' : ''} size={21} weight="fill" />
          <select aria-label="系统音频设备"><option>系统默认输出</option></select>
        </div>
        <div className="settings-row">
          <Microphone size={25} />
          <div><strong>麦克风</strong><span>MacBook Pro 麦克风 · 16kHz 单声道</span></div>
          <CheckCircle className={online ? 'success-icon' : ''} size={21} weight="fill" />
          <select aria-label="麦克风设备"><option>MacBook Pro 麦克风</option></select>
        </div>
      </div>

      <div className="permissions-section">
        <h2>系统权限</h2>
        <p>桌面 Agent 仅在任务运行期间使用下列权限。</p>
        <span><ShieldCheck size={21} weight="duotone" /><b>屏幕与系统音频录制</b><em><CheckCircle size={18} weight="fill" />{online ? '由任务预检确认' : '等待 Agent'}</em></span>
        <span><Microphone size={21} weight="duotone" /><b>麦克风访问</b><em><CheckCircle size={18} weight="fill" />{online ? '由任务预检确认' : '等待 Agent'}</em></span>
        <span><Keyboard size={21} weight="duotone" /><b>全局快捷键</b><em><CheckCircle size={18} weight="fill" />{online ? 'Agent 已接管' : '等待 Agent'}</em></span>
      </div>
    </section>
  )
}
