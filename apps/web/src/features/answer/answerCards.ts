import type { RealtimeEvent } from '../../shared/protocol'

export interface AnswerCard {
  id: string
  question: string
  answer: string
  code: string
  language: string
  complexity: string
  contentKind: string
  source: string
  mode: string
  generating: boolean
  cancelled: boolean
  error: string
  createdAt: number
}

const ANSWER_EVENTS = new Set([
  'focus.updated',
  'answer.started',
  'answer.delta',
  'answer.completed',
  'answer.cancelled',
  'error',
])

export function applyAnswerEvent(cards: AnswerCard[], event: RealtimeEvent): AnswerCard[] {
  if (!ANSWER_EVENTS.has(event.type)) return cards
  const payload = event.payload
  if (event.type === 'focus.updated') {
    const question = String(payload.question ?? '').trim()
    if (!question) return cards
    const focusID = String(payload.focus_id ?? event.event_id)
    if (cards.some((card) => card.id === focusID)) return cards
    const latest = cards.at(-1)
    if (latest?.question === question && !latest.answer) {
      return replaceLatest(cards, {
        ...latest,
        mode: String(payload.mode ?? latest.mode),
        contentKind: String(payload.content_kind ?? latest.contentKind),
        source: String(payload.source ?? latest.source),
        language: String(payload.language ?? latest.language),
        error: '',
      })
    }
    return [
      ...cards.slice(-49),
      {
        id: focusID,
        question,
        answer: '',
        code: '',
        language: '',
        complexity: '',
        contentKind: String(payload.content_kind ?? 'KNOWLEDGE'),
        source: String(payload.source ?? 'VOICE'),
        mode: String(payload.mode ?? ''),
        generating: false,
        cancelled: false,
        error: '',
        createdAt: event.created_at,
      },
    ]
  }
  const focusID = String(payload.focus_id ?? '')
  const targetIndex = focusID ? cards.findIndex((card) => card.id === focusID) : cards.length - 1
  if (targetIndex < 0) return cards
  const target = cards[targetIndex]
  if (event.type === 'answer.started') {
    return replaceAt(cards, targetIndex, { ...target, answer: '', generating: true, cancelled: false, error: '' })
  }
  if (event.type === 'answer.delta') {
    return replaceAt(cards, targetIndex, { ...target, answer: target.answer + String(payload.delta ?? ''), generating: true })
  }
  if (event.type === 'answer.completed') {
    return replaceAt(cards, targetIndex, {
      ...target,
      answer: String(payload.answer ?? ''),
      code: String(payload.code ?? target.code),
      language: String(payload.language ?? target.language),
      complexity: String(payload.complexity ?? target.complexity),
      contentKind: String(payload.content_kind ?? target.contentKind),
      source: String(payload.source ?? target.source),
      mode: String(payload.mode ?? target.mode),
      generating: false,
      cancelled: false,
    })
  }
  if (event.type === 'answer.cancelled') {
    return replaceAt(cards, targetIndex, { ...target, generating: false, cancelled: true })
  }
  return replaceAt(cards, targetIndex, { ...target, generating: false, error: String(payload.message ?? '生成回答时出现问题') })
}

function replaceLatest(cards: AnswerCard[], latest: AnswerCard): AnswerCard[] {
  return [...cards.slice(0, -1), latest]
}

function replaceAt(cards: AnswerCard[], index: number, card: AnswerCard): AnswerCard[] {
  return cards.map((current, currentIndex) => currentIndex === index ? card : current)
}
