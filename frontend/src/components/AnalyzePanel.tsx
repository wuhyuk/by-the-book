// 문장 입력 (VS3). 문장은 이 컴포넌트 상태에만 두고 URL·localStorage·콘솔에 남기지 않는다.
import { useState, type FormEvent } from 'react'
import { ANALYZE_TEXT } from '../texts'

const MAX_LENGTH = 2000

interface Props {
  onAnalyze: (text: string) => void
  analyzing: boolean
}

export function AnalyzePanel({ onAnalyze, analyzing }: Props) {
  const [text, setText] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (text.trim() !== '') onAnalyze(text)
  }
  return (
    <form className="analyze" onSubmit={submit} autoComplete="off" noValidate data-testid="analyze-form">
      <h2>{ANALYZE_TEXT.title}</h2>
      <label htmlFor="situation" className="visually-hidden">
        {ANALYZE_TEXT.label}
      </label>
      <textarea
        id="situation"
        name="situation"
        rows={4}
        maxLength={MAX_LENGTH}
        autoComplete="off"
        spellCheck={false}
        placeholder={ANALYZE_TEXT.placeholder}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <p className="privacy" data-testid="privacy">
        {ANALYZE_TEXT.privacy}
      </p>
      <p className="hint">{ANALYZE_TEXT.calcNote}</p>
      <div className="analyze-actions">
        <button type="submit" disabled={analyzing || text.trim() === ''}>
          {analyzing ? ANALYZE_TEXT.analyzing : ANALYZE_TEXT.button}
        </button>
        <span className="hint">
          {text.length.toLocaleString('ko-KR')} / {MAX_LENGTH.toLocaleString('ko-KR')}자 · {ANALYZE_TEXT.or}
        </span>
      </div>
    </form>
  )
}
