import type { RealtimeEvent } from '../../shared/protocol'

export type ScreenshotStatus = 'idle' | 'analyzing' | 'completed' | 'no_question' | 'timeout' | 'error' | 'cancelled'

export interface ScreenshotState {
  status: ScreenshotStatus
  screenshotId: string
  startedAt: number | null
  durationMs: number | null
}

export const EMPTY_SCREENSHOT_STATE: ScreenshotState = {
  status: 'idle',
  screenshotId: '',
  startedAt: null,
  durationMs: null,
}

export function applyScreenshotEvent(current: ScreenshotState, event: RealtimeEvent): ScreenshotState {
  if (event.type === 'screenshot.accepted') {
    return {
      status: 'analyzing',
      screenshotId: String(event.payload.screenshot_id ?? ''),
      startedAt: event.created_at,
      durationMs: null,
    }
  }
  if (event.type === 'screenshot.focus.released') {
    return {
      status: normalizeStatus(String(event.payload.outcome ?? 'error')),
      screenshotId: String(event.payload.screenshot_id ?? current.screenshotId),
      startedAt: current.startedAt,
      durationMs: Number(event.payload.duration_ms ?? 0) || null,
    }
  }
  if (event.type === 'error' && event.payload.operation === 'screenshot_focus') {
    return { ...current, status: 'error' }
  }
  return current
}

function normalizeStatus(value: string): ScreenshotStatus {
  if (value === 'completed' || value === 'no_question' || value === 'timeout' || value === 'cancelled') return value
  return 'error'
}
