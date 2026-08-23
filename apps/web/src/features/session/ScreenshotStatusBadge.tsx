import { CheckCircle, ImageSquare, SpinnerGap, WarningCircle } from '@phosphor-icons/react'
import { memo, useEffect, useState } from 'react'

import type { ScreenshotState } from './screenshotState'

export const ScreenshotStatusBadge = memo(function ScreenshotStatusBadge({ state, compact = false }: { state: ScreenshotState; compact?: boolean }) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (state.status !== 'analyzing') return
    setNow(Date.now())
    const timer = window.setInterval(() => setNow(Date.now()), 1_000)
    return () => window.clearInterval(timer)
  }, [state.status, state.startedAt])

  if (state.status === 'idle') return null
  const durationMs = state.durationMs ?? (state.startedAt ? Math.max(0, now - state.startedAt * 1_000) : 0)
  const seconds = `${Math.floor(durationMs / 1_000)}s`
  const content = statusContent(state.status, seconds)
  return <span className={`screenshot-status screenshot-status--${state.status}${compact ? ' screenshot-status--compact' : ''}`}>{content.icon}<span>{content.label}</span></span>
})

function statusContent(status: ScreenshotState['status'], seconds: string) {
  if (status === 'analyzing') return { icon: <SpinnerGap className="spin" size={15} />, label: `截图分析中 · ${seconds}` }
  if (status === 'completed') return { icon: <CheckCircle size={15} weight="fill" />, label: `截图已完成 · ${seconds}` }
  if (status === 'no_question') return { icon: <ImageSquare size={15} />, label: `未识别到题目 · ${seconds}` }
  if (status === 'timeout') return { icon: <WarningCircle size={15} weight="fill" />, label: `截图分析超时 · ${seconds}` }
  if (status === 'cancelled') return { icon: <WarningCircle size={15} />, label: '截图分析已取消' }
  return { icon: <WarningCircle size={15} weight="fill" />, label: '截图分析失败' }
}
