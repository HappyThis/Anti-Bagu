const QUESTION_TITLE_LIMIT = 60
const QUESTION_DETAIL_BOUNDARY =
  /\s+(?=(?:给你|给定|请你|请实现|实现一个|编写一个|算法如下|示例\s*\d*\s*[:：]|输入\s*[:：]|输出\s*[:：]|提示\s*[:：]))/
const FENCED_CODE = /```(?:python)?\s*[\s\S]*?```/gi

export function conciseQuestionTitle(question: string): string {
  const normalized = question.replace(/\s+/g, ' ').trim()
  if (!normalized) return ''
  const beforeDetail = normalized.split(QUESTION_DETAIL_BOUNDARY, 1)[0]?.trim()
  const candidate = beforeDetail && beforeDetail.length >= 4 ? beforeDetail : normalized
  const characters = Array.from(candidate)
  if (characters.length <= QUESTION_TITLE_LIMIT) return candidate
  return `${characters.slice(0, QUESTION_TITLE_LIMIT).join('')}…`
}

export function answerWithoutDuplicateCode(answer: string, code: string): string {
  const normalized = answer.trim()
  if (!code.trim()) return normalized
  return normalized
    .replace(FENCED_CODE, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}
