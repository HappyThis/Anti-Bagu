interface AnswerWorkspaceProps {
  focus: string
  answer: string
  mode: string
  generating: boolean
  error: string
  onClear: () => void
}

export function AnswerWorkspace({
  focus,
  answer,
  mode,
  generating,
  error,
  onClear,
}: AnswerWorkspaceProps) {
  return (
    <div className="answer-workspace">
      <section className="focus-panel">
        <span className="section-label">当前问题</span>
        <h1>{focus || '等待面试官提出问题'}</h1>
      </section>
      <section className="answer-panel" aria-live="polite">
        <header>
          <div>
            <span className="section-label section-label--answer">建议回答</span>
            {mode ? <span className="mode-text">{mode}</span> : null}
          </div>
          <button type="button" onClick={onClear}>清空</button>
        </header>
        {error ? <p className="error-copy">{error}</p> : null}
        <p className={answer ? 'answer-copy' : 'answer-copy answer-copy--empty'}>
          {answer || '识别到完整问题后，回答会显示在这里。'}
          {generating ? <span className="cursor" aria-hidden="true" /> : null}
        </p>
      </section>
    </div>
  )
}
