import { describe, expect, it } from 'vitest'

import type { RealtimeEvent } from '../../shared/protocol'
import { applyAnswerEvent, type AnswerCard } from './answerCards'

function event(
  type: string,
  payload: Record<string, unknown>,
  index: number,
): RealtimeEvent {
  return {
    type,
    event_id: `event-${index}`,
    session_id: 'task',
    conversation_revision: index,
    created_at: index,
    payload,
  }
}

function appendAnswer(cards: AnswerCard[], index: number): AnswerCard[] {
  const focusId = `focus-${index}`
  const focused = applyAnswerEvent(
    cards,
    event(
      'focus.updated',
      { focus_id: focusId, question: `问题 ${index}`, source: 'VOICE' },
      index,
    ),
  )
  return applyAnswerEvent(
    focused,
    event(
      'answer.completed',
      {
        focus_id: focusId,
        question: `问题 ${index}`,
        answer: `回答 ${index}`,
        source: 'VOICE',
      },
      index,
    ),
  )
}

describe('answer cards', () => {
  it('keeps all cards after the old fifty-card boundary', () => {
    let cards: AnswerCard[] = []
    for (let index = 1; index <= 106; index += 1) {
      cards = appendAnswer(cards, index)
    }

    expect(cards).toHaveLength(106)
    expect(cards[0].question).toBe('问题 1')
    expect(cards.at(-1)?.answer).toBe('回答 106')
  })

  it('restores a complete ordered snapshot after refresh', () => {
    let source: AnswerCard[] = []
    for (let index = 1; index <= 106; index += 1) {
      source = appendAnswer(source, index)
    }
    const cards = applyAnswerEvent(
      [],
      event(
        'answer.snapshot',
        {
          cards: source.map((card) => ({ ...card, created_at: card.createdAt })),
          total_count: source.length,
        },
        107,
      ),
    )

    expect(cards).toHaveLength(106)
    expect(cards[0].id).toBe('focus-1')
    expect(cards.at(-1)?.id).toBe('focus-106')
  })

  it('updates an existing focus without creating another card', () => {
    const initial = appendAnswer([], 1)
    const revised = applyAnswerEvent(
      initial,
      event(
        'answer.completed',
        {
          focus_id: 'focus-1',
          question: '问题 1',
          answer: '补充后的回答',
          code: 'print(1)',
          source: 'VOICE',
        },
        2,
      ),
    )

    expect(revised).toHaveLength(1)
    expect(revised[0].answer).toBe('补充后的回答')
    expect(revised[0].code).toBe('print(1)')
  })
})
