import { describe, expect, it } from 'vitest'

import type { RealtimeEvent } from '../../shared/protocol'
import { applyAnswerEvent, type AnswerCard } from './answerCards'
import { answerWithoutDuplicateCode, conciseQuestionTitle } from './presentation'

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

  it('turns a screenshot problem statement into a short display title', () => {
    const title = conciseQuestionTitle(
      '1331. 数组序号转换 给你一个整数数组 arr，请你将数组中的每个元素替换为它们排序后的序号。示例 1：输入 arr = [40,10,20,30]',
    )

    expect(title).toBe('1331. 数组序号转换')
    expect(Array.from(title).length).toBeLessThanOrEqual(60)
  })

  it('removes code duplicated inside the answer when code has its own pane', () => {
    const answer = answerWithoutDuplicateCode(
      '先排序并建立映射。\n```python\ndef solve():\n  pass\n```\n复杂度 O(n log n)。',
      'def solve():\n  pass',
    )

    expect(answer).toBe('先排序并建立映射。\n\n复杂度 O(n log n)。')
  })
})
