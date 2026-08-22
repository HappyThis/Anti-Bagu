import { CheckCircle, DeviceMobile, WarningCircle, Waveform } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { websocketUrl } from '../../shared/api'
import type { RealtimeEvent } from '../../shared/protocol'

export function MobileCompanionPage() {
  const { pairingToken = '' } = useParams()
  const [connection, setConnection] = useState<'connecting' | 'connected' | 'expired'>('connecting')
  const [focus, setFocus] = useState('等待面试官提出问题')
  const [answer, setAnswer] = useState('建议回答会在识别到完整问题后显示。')
  const [generating, setGenerating] = useState(false)

  useEffect(() => {
    const socket = new WebSocket(websocketUrl(`/ws/mobile/${pairingToken}`))
    socket.addEventListener('open', () => setConnection('connected'))
    socket.addEventListener('close', (event) => {
      setConnection(event.code === 4404 ? 'expired' : 'connecting')
    })
    socket.addEventListener('message', (message) => {
      const event = JSON.parse(message.data) as RealtimeEvent
      if (event.type === 'focus.updated') {
        setFocus(String(event.payload.question ?? ''))
        setAnswer('正在生成建议回答…')
      } else if (event.type === 'answer.started') {
        setGenerating(true)
        setAnswer('')
      } else if (event.type === 'answer.delta') {
        setAnswer((current) => current + String(event.payload.delta ?? ''))
      } else if (event.type === 'answer.completed') {
        setGenerating(false)
        setAnswer(String(event.payload.answer ?? ''))
      }
    })
    return () => socket.close()
  }, [pairingToken])

  if (connection === 'expired') {
    return (
      <main className="mobile-companion-page mobile-companion-page--centered">
        <WarningCircle size={48} weight="duotone" />
        <h1>配对链接已失效</h1>
        <p>请回到电脑端任务页面重新生成二维码。</p>
      </main>
    )
  }

  return (
    <main className="mobile-companion-page">
      <header>
        <span className="mobile-brand"><DeviceMobile size={21} weight="duotone" />Anti-Bagu</span>
        <span className={`mobile-live-state mobile-live-state--${connection}`}><i />{connection === 'connected' ? '已连接' : '正在连接'}</span>
      </header>
      <section className="mobile-focus-card">
        <span><Waveform size={17} />当前问题</span>
        <h1>{focus}</h1>
      </section>
      <section className="mobile-answer-card">
        <div><span>建议回答</span>{generating ? <em>生成中</em> : <CheckCircle size={18} weight="fill" />}</div>
        <p>{answer}{generating ? <i className="cursor" /> : null}</p>
      </section>
      <footer>请保持屏幕常亮 · 任务结束后连接会自动关闭</footer>
    </main>
  )
}
