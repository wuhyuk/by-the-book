// 문장 입력 (VS3). 문장은 이 컴포넌트 상태에만 두고 URL·localStorage·콘솔에 남기지 않는다.
import { useState, type FormEvent } from 'react'
import { ANALYZE_TEXT, APP_TEXT } from '../texts'

const MAX_LENGTH = 2000

interface Props {
  onAnalyze: (text: string) => void
  analyzing: boolean
  /** 품목별 예시 문장 (기본: 헬스장 예시) */
  placeholder?: string
  /** 같은 화면에 품목별 패널이 둘 있어 id를 나눈다 */
  idPrefix?: string
  /** 누르면 입력창에 채우는 예시 문장 */
  examples?: readonly string[]
}

export function AnalyzePanel({ onAnalyze, analyzing, placeholder = ANALYZE_TEXT.placeholder, idPrefix = '', examples = [] }: Props) {
  const [text, setText] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (text.trim() !== '') onAnalyze(text)
  }
  return (
    <form className="analyze" onSubmit={submit} autoComplete="off" noValidate data-testid="analyze-form">
      <h2>{ANALYZE_TEXT.title}</h2>
      {examples.length > 0 && (
        <div className="examples" data-testid="examples">
          <p className="hint">{APP_TEXT.examplesTitle}</p>
          {examples.map((ex, i) => (
            <button
              key={i}
              type="button"
              className="example-button"
              onClick={() => setText(ex)}
              data-testid={`example-${i}`}
            >
              {ex}
            </button>
          ))}
        </div>
      )}
      <label htmlFor={`${idPrefix}situation`} className="visually-hidden">
        {ANALYZE_TEXT.label}
      </label>
      <textarea
        id={`${idPrefix}situation`}
        name="situation"
        rows={4}
        maxLength={MAX_LENGTH}
        autoComplete="off"
        spellCheck={false}
        placeholder={placeholder}
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
