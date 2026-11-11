// 복사 버튼이 있는 글 묶음. navigator.clipboard가 실패하면(권한·비보안 주소 등) 선택 가능한 글 상자로 대체한다.
// 글은 서버 응답(/api/guide) 그대로이며 화면에서 숫자를 만들지 않는다.
import { useRef, useState } from 'react'
import { GUIDE_TEXT } from '../texts'

interface Props {
  title: string
  buttonLabel: string
  /** 화면에 보이는 형태 (줄 목록) */
  lines: readonly string[]
  testId: string
}

type CopyState = 'idle' | 'copied' | 'failed'

export function CopyBlock({ title, buttonLabel, lines, testId }: Props) {
  const [state, setState] = useState<CopyState>('idle')
  const fallbackRef = useRef<HTMLTextAreaElement>(null)
  const text = lines.join('\n')

  const copy = async () => {
    try {
      if (!navigator.clipboard) throw new Error('clipboard unavailable')
      await navigator.clipboard.writeText(text)
      setState('copied')
    } catch {
      setState('failed')
      // 대체 상자가 그려진 뒤 전체 선택해 둔다
      setTimeout(() => fallbackRef.current?.select(), 0)
    }
  }

  return (
    <div className="copy-block" data-testid={testId}>
      <div className="copy-head">
        <h4>{title}</h4>
        <button type="button" className="copy-button" onClick={copy} data-testid={`${testId}-copy`}>
          {buttonLabel}
        </button>
      </div>
      {lines.map((line, i) => (
        <p key={i} className="copy-line">
          {line}
        </p>
      ))}
      {state === 'copied' && (
        <p className="copy-status" role="status">
          {GUIDE_TEXT.copied}
        </p>
      )}
      {state === 'failed' && (
        <>
          <p className="copy-status" role="status">
            {GUIDE_TEXT.copyFailed}
          </p>
          <textarea
            ref={fallbackRef}
            className="copy-fallback"
            readOnly
            rows={Math.min(lines.length + 1, 10)}
            value={text}
            onFocus={(e) => e.currentTarget.select()}
            aria-label={title}
            data-testid={`${testId}-fallback`}
          />
        </>
      )}
    </div>
  )
}
