import { ArrowLeft, ArrowRight, Bell, Code, Trash } from '@phosphor-icons/react'
import { memo, useEffect, useLayoutEffect, useRef, useState } from 'react'

import type { AnswerCard } from './answerCards'

export function AnswerCardCarousel({ cards, onClear }: { cards: AnswerCard[]; onClear: () => void }) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const previousLength = useRef(cards.length)
  const initialized = useRef(false)
  const [index, setIndex] = useState(Math.max(0, cards.length - 1))
  const [unseen, setUnseen] = useState(false)

  useLayoutEffect(() => {
    if (!initialized.current && cards.length) {
      initialized.current = true
      previousLength.current = cards.length
      moveTo(cards.length - 1, 'auto')
    }
  }, [cards.length])

  useEffect(() => {
    if (cards.length <= previousLength.current) {
      previousLength.current = cards.length
      return
    }
    const wasLatest = index >= previousLength.current - 1
    previousLength.current = cards.length
    if (wasLatest) {
      moveTo(cards.length - 1)
    } else {
      setUnseen(true)
    }
  }, [cards.length, index])

  function moveTo(nextIndex: number, behavior: ScrollBehavior = 'smooth') {
    const bounded = Math.min(Math.max(0, nextIndex), Math.max(0, cards.length - 1))
    setIndex(bounded)
    if (bounded === cards.length - 1) setUnseen(false)
    const viewport = viewportRef.current
    if (viewport) viewport.scrollTo({ left: bounded * viewport.clientWidth, behavior })
  }

  function updateIndexFromScroll() {
    const viewport = viewportRef.current
    if (!viewport || viewport.clientWidth === 0) return
    const nextIndex = Math.round(viewport.scrollLeft / viewport.clientWidth)
    setIndex(nextIndex)
    if (nextIndex === cards.length - 1) setUnseen(false)
  }

  return (
    <section className="answer-carousel" aria-label="问题与建议回答">
      <header>
        <div><span>问题与回答</span><strong>{cards.length ? `${index + 1} / ${cards.length}` : '等待提问'}</strong>{cards.length > 1 ? <small>左右滑动切换问题</small> : null}</div>
        <div className="answer-carousel-actions">
          {unseen ? <button className="new-answer-button" type="button" onClick={() => moveTo(cards.length - 1)}><Bell size={15} weight="fill" />有新回答</button> : null}
          <button type="button" aria-label="上一个问题" disabled={!cards.length || index === 0} onClick={() => moveTo(index - 1)}><ArrowLeft size={17} /></button>
          <button type="button" aria-label="下一个问题" disabled={!cards.length || index === cards.length - 1} onClick={() => moveTo(index + 1)}><ArrowRight size={17} /></button>
          <button type="button" aria-label="清空问题和回答" disabled={!cards.length} onClick={onClear}><Trash size={17} /></button>
        </div>
      </header>
      <div className="answer-carousel-viewport" ref={viewportRef} onScroll={updateIndexFromScroll}>
        {cards.length ? cards.map((card) => <DesktopAnswerCard card={card} key={card.id} />) : <div className="answer-slide answer-slide--empty"><span>当前问题</span><h2>等待面试官提出问题</h2><p>识别到完整问题后，建议回答会显示在这里。</p></div>}
      </div>
      {cards.length > 1 && cards.length <= 30 ? <div className="answer-carousel-dots" aria-hidden="true">{cards.map((card, cardIndex) => <i className={cardIndex === index ? 'active' : ''} key={card.id} />)}</div> : null}
    </section>
  )
}

const DesktopAnswerCard = memo(function DesktopAnswerCard({ card }: { card: AnswerCard }) {
  const [pane, setPane] = useState<'answer' | 'code'>('answer')
  const hasCode = Boolean(card.code)
  return (
    <article className="answer-slide">
      <div className="answer-slide-question"><div className="answer-question-meta"><span>当前问题</span>{hasCode ? <em><Code size={14} />包含 Python 代码</em> : null}</div><h2>{card.question}</h2></div>
      <div className="answer-slide-response">
        <header>
          <div className="answer-content-heading">
            <span>{hasCode ? '解题思路' : '建议回答'}</span>
            {card.source === 'SCREENSHOT' ? <em>截图识别</em> : null}
            {card.generating ? <em>生成中</em> : card.cancelled ? <em>已切换问题</em> : card.answer ? <em>已准备</em> : null}
          </div>
          {hasCode ? <div className="answer-pane-tabs" role="tablist" aria-label="解题内容"><button className={pane === 'answer' ? 'active' : ''} type="button" role="tab" aria-selected={pane === 'answer'} onClick={() => setPane('answer')}>解题思路</button><button className={pane === 'code' ? 'active' : ''} type="button" role="tab" aria-selected={pane === 'code'} onClick={() => setPane('code')}><Code size={15} />Python 代码</button></div> : null}
        </header>
        {card.error ? <p className="error-copy">{card.error}</p> : null}
        {pane === 'code' && hasCode ? <div className="answer-code-pane"><pre><code>{card.code}</code></pre></div> : <p className={card.answer ? '' : 'answer-placeholder'}>{card.answer || (card.generating ? '正在生成建议回答…' : '建议回答准备中…')}{card.generating ? <i className="cursor" /> : null}</p>}
      </div>
    </article>
  )
})
