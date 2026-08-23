import { Bell, CheckCircle, WarningCircle, Waveform } from '@phosphor-icons/react'
import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import { applyAnswerEvent, type AnswerCard } from '../../features/answer/answerCards'
import { ScreenshotStatusBadge } from '../../features/session/ScreenshotStatusBadge'
import { applyScreenshotEvent, EMPTY_SCREENSHOT_STATE } from '../../features/session/screenshotState'
import { websocketUrl } from '../../shared/api'
import type { RealtimeEvent } from '../../shared/protocol'

export function MobileCompanionPage() {
  const { pairingToken = '' } = useParams()
  const feedRef = useRef<HTMLDivElement>(null)
  const browsingHistory = useRef(false)
  const anchorCardId = useRef('')
  const previousNewestCardId = useRef('')
  const [connection, setConnection] = useState<'connecting' | 'connected' | 'expired'>('connecting')
  const [cards, setCards] = useState<AnswerCard[]>([])
  const [screenshot, setScreenshot] = useState(EMPTY_SCREENSHOT_STATE)
  const [hasNewAnswer, setHasNewAnswer] = useState(false)

  useEffect(() => {
    let disposed = false
    let reconnectTimer: number | undefined
    let socket: WebSocket | undefined
    const connect = () => {
      if (disposed) return
      setConnection('connecting')
      socket = new WebSocket(websocketUrl(`/ws/mobile/${pairingToken}`))
      socket.addEventListener('open', () => {
        if (!disposed) setConnection('connected')
      })
      socket.addEventListener('close', (event) => {
        if (disposed) return
        if (event.code === 4404) {
          setConnection('expired')
          return
        }
        setConnection('connecting')
        reconnectTimer = window.setTimeout(connect, 1_500)
      })
      socket.addEventListener('message', (message) => {
        if (disposed) return
        try {
          const event = JSON.parse(message.data) as RealtimeEvent
          setCards((current) => applyAnswerEvent(current, event))
          setScreenshot((current) => applyScreenshotEvent(current, event))
        } catch {
          // The server records malformed protocol messages.
        }
      })
    }
    connect()
    return () => {
      disposed = true
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [pairingToken])

  useLayoutEffect(() => {
    const feed = feedRef.current
    if (!feed) return
    const newestCardId = cards.at(-1)?.id ?? ''
    const previousNewest = previousNewestCardId.current
    if (!newestCardId) {
      previousNewestCardId.current = ''
      anchorCardId.current = ''
      return
    }
    if (!previousNewest) {
      feed.scrollTo({ top: 0, behavior: 'auto' })
    } else if (newestCardId !== previousNewest) {
      if (browsingHistory.current && anchorCardId.current) {
        const anchor = Array.from(feed.children).find(
          (element) => (element as HTMLElement).dataset.cardId === anchorCardId.current,
        ) as HTMLElement | undefined
        if (anchor) {
          feed.scrollTop +=
            anchor.getBoundingClientRect().top - feed.getBoundingClientRect().top
        }
        setHasNewAnswer(true)
      } else {
        feed.scrollTo({ top: 0, behavior: 'smooth' })
      }
    }
    previousNewestCardId.current = newestCardId
  }, [cards])

  useEffect(() => {
    if (screenshot.status === 'idle' || screenshot.status === 'analyzing') return
    const screenshotId = screenshot.screenshotId
    const timer = window.setTimeout(() => {
      setScreenshot((current) => current.screenshotId === screenshotId ? EMPTY_SCREENSHOT_STATE : current)
    }, 4_000)
    return () => window.clearTimeout(timer)
  }, [screenshot.screenshotId, screenshot.status])

  const newestFirst = useMemo(() => [...cards].reverse(), [cards])

  function showNewestAnswer() {
    browsingHistory.current = false
    anchorCardId.current = newestFirst[0]?.id ?? ''
    feedRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
    setHasNewAnswer(false)
  }

  function handleFeedScroll() {
    const feed = feedRef.current
    if (!feed?.clientHeight) return
    const index = Math.min(
      newestFirst.length - 1,
      Math.max(0, Math.round(feed.scrollTop / feed.clientHeight)),
    )
    const browsing = index > 0
    browsingHistory.current = browsing
    anchorCardId.current = newestFirst[index]?.id ?? ''
    if (!browsing) setHasNewAnswer(false)
  }

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
    <main className="mobile-companion-page mobile-companion-page--answers">
      <header>
        <span className="mobile-brand"><img src="/brand/anti-bagu-logo.png" alt="" />Anti-Bagu</span>
        {screenshot.status !== 'idle' ? <ScreenshotStatusBadge compact state={screenshot} /> : <span className={`mobile-live-state mobile-live-state--${connection}`}><i />{connection === 'connected' ? '已连接' : '正在连接'}</span>}
      </header>
      {hasNewAnswer ? <button className="mobile-new-answer" type="button" onClick={showNewestAnswer}><Bell size={15} weight="fill" />有新回答</button> : null}
      <div className="mobile-answer-feed" ref={feedRef} onScroll={handleFeedScroll}>
        {newestFirst.length ? newestFirst.map((card, index) => <MobileAnswerSlide card={card} position={cards.length - index} total={cards.length} key={card.id} />) : (
          <article className="mobile-answer-slide mobile-answer-slide--empty">
            <section className="mobile-qa-card"><header><span className="mobile-answer-index">等待中</span></header><div className="mobile-question-block"><span><Waveform size={14} />当前问题</span><h1>等待面试官提出问题</h1></div><div className="mobile-response-block"><span>建议回答</span><AutoFitAnswer text="识别到完整问题后，建议回答会显示在这里。" generating={false} /></div></section>
          </article>
        )}
      </div>
    </main>
  )
}

const MobileAnswerSlide = memo(function MobileAnswerSlide({ card, position, total }: { card: AnswerCard; position: number; total: number }) {
  return (
    <article className="mobile-answer-slide" data-card-id={card.id}>
      <section className="mobile-qa-card">
        <header><span className="mobile-answer-index">{position} / {total}</span>{card.generating ? <em>生成中</em> : card.cancelled ? <em>已切换</em> : <CheckCircle size={17} weight="fill" />}</header>
        <div className="mobile-question-block">
          <span><Waveform size={14} />问题</span>
          <h1>{card.question}</h1>
        </div>
        <MobileCardContent card={card} />
      </section>
    </article>
  )
})

function MobileCardContent({ card }: { card: AnswerCard }) {
  const panesRef = useRef<HTMLDivElement>(null)
  const [pane, setPane] = useState(0)
  const hasCode = Boolean(card.code)

  if (!hasCode) {
    return <div className="mobile-response-block"><span>建议回答</span>{card.error ? <p className="error-copy">{card.error}</p> : null}<AutoFitAnswer text={card.answer || (card.generating ? '正在生成建议回答…' : '建议回答准备中…')} generating={card.generating} /></div>
  }

  return (
    <div className="mobile-card-content">
      <div className="mobile-card-panes" ref={panesRef} onScroll={() => { const viewport = panesRef.current; if (viewport?.clientWidth) setPane(Math.round(viewport.scrollLeft / viewport.clientWidth)) }}>
        <section className="mobile-response-block mobile-card-pane">
          <span>解题思路</span>
          {card.error ? <p className="error-copy">{card.error}</p> : null}
          <AutoFitAnswer text={card.answer || '正在整理解题思路…'} generating={card.generating} />
        </section>
        <section className="mobile-code-block mobile-card-pane">
          <span>Python 代码</span>
          <AutoFitCode code={card.code} />
        </section>
      </div>
      <div className="mobile-pane-indicator" aria-label={pane === 0 ? '当前显示解题思路，向左滑查看代码' : '当前显示代码，向右滑查看解题思路'}><i className={pane === 0 ? 'active' : ''} /><i className={pane === 1 ? 'active' : ''} /><span>{pane === 0 ? '左滑看代码' : '右滑看思路'}</span></div>
    </div>
  )
}

function AutoFitAnswer({ text, generating }: { text: string; generating: boolean }) {
  const copyRef = useRef<HTMLParagraphElement>(null)

  useLayoutEffect(() => {
    const element = copyRef.current
    if (!element) return
    const fit = () => {
      let fontSize = 16
      element.style.fontSize = `${fontSize}px`
      while (element.scrollHeight > element.clientHeight && fontSize > 9) {
        fontSize -= 0.5
        element.style.fontSize = `${fontSize}px`
      }
    }
    const frame = window.requestAnimationFrame(fit)
    const observer = new ResizeObserver(fit)
    observer.observe(element.parentElement ?? element)
    return () => {
      window.cancelAnimationFrame(frame)
      observer.disconnect()
    }
  }, [text])

  return <p className="mobile-answer-copy" ref={copyRef}>{text}{generating ? <i className="cursor" /> : null}</p>
}

function AutoFitCode({ code }: { code: string }) {
  const codeRef = useRef<HTMLElement>(null)

  useLayoutEffect(() => {
    const element = codeRef.current
    if (!element) return
    const fit = () => {
      let fontSize = 12
      element.style.fontSize = `${fontSize}px`
      while ((element.scrollHeight > element.clientHeight || element.scrollWidth > element.clientWidth) && fontSize > 7) {
        fontSize -= 0.5
        element.style.fontSize = `${fontSize}px`
      }
    }
    const frame = window.requestAnimationFrame(fit)
    const observer = new ResizeObserver(fit)
    observer.observe(element)
    return () => {
      window.cancelAnimationFrame(frame)
      observer.disconnect()
    }
  }, [code])

  return <div className="mobile-code-copy"><code ref={codeRef}>{code}</code></div>
}
