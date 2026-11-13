// 설명·업체용 문안 (POST /api/guide). 계산에 보낸 입력을 그대로 다시 보내고 서버가 다시 계산한 문안을 보여 준다.
// 숫자는 서버 문안 그대로다 (화면에서 만들지 않는다). 업체용 문안이 null이면(❔·계산 안 함·규칙 미검증) 그 영역을 숨긴다.
import { useEffect, useState } from 'react'
import { fetchGuide } from '../api'
import { APP_TEXT, GUIDE_TEXT } from '../texts'
import type { Guide, GymInput, Item, LaundryInput } from '../types'
import { CopyBlock } from './CopyBlock'

interface Props {
  item: Item
  input: GymInput | LaundryInput
  surveyUrl: string | null
}

type State = { kind: 'loading' } | { kind: 'ok'; guide: Guide } | { kind: 'error' }
/** 받은 응답과 그 응답을 요청한 입력. 입력이 바뀌면 새 응답이 올 때까지 '불러오는 중'으로 본다 */
type Loaded = { input: GymInput | LaundryInput; state: State }

export function GuidePanel({ item, input, surveyUrl }: Props) {
  const [loaded, setLoaded] = useState<Loaded | null>(null)

  useEffect(() => {
    let alive = true
    fetchGuide(item, input).then((outcome) => {
      if (!alive) return
      setLoaded({ input, state: outcome.kind === 'ok' ? { kind: 'ok', guide: outcome.data } : { kind: 'error' } })
    })
    return () => {
      alive = false
    }
  }, [item, input])

  const state: State = loaded && loaded.input === input ? loaded.state : { kind: 'loading' }
  const mentions1372 = state.kind === 'ok' && state.guide.explanation.some((line) => line.includes('1372'))

  return (
    <section className="guide-panel" aria-label={GUIDE_TEXT.title} data-testid="guide">
      <h3>{GUIDE_TEXT.title}</h3>
      {state.kind === 'loading' && <p className="hint">{GUIDE_TEXT.loading}</p>}
      {state.kind === 'error' && (
        <p className="request-error" role="alert">
          {GUIDE_TEXT.loadFailed}
        </p>
      )}
      {state.kind === 'ok' && (
        <>
          <CopyBlock
            title={GUIDE_TEXT.explanationTitle}
            buttonLabel={GUIDE_TEXT.copyExplanation}
            lines={state.guide.explanation}
            testId="guide-explanation"
          />
          {state.guide.company_message !== null && (
            <CopyBlock
              title={GUIDE_TEXT.companyTitle}
              buttonLabel={GUIDE_TEXT.copyCompany}
              lines={state.guide.company_message.split('\n')}
              testId="guide-company"
            />
          )}
        </>
      )}
      <div className="result-help">
        <p className="disclaimer">{APP_TEXT.disclaimer}</p>
        {/* 설명에 이미 1372 안내가 있으면(❔ 등) 같은 안내를 한 번 더 쓰지 않는다 */}
        {!mentions1372 && <p data-testid="consult-1372">{APP_TEXT.consult1372}</p>}
        {surveyUrl && (
          <a className="survey-button" href={surveyUrl} target="_blank" rel="noopener noreferrer" data-testid="survey">
            {APP_TEXT.survey}
          </a>
        )}
      </div>
    </section>
  )
}
