// 설명·업체용 문안 (POST /api/guide). 계산에 보낸 입력을 그대로 다시 보내고 서버가 다시 계산한 문안을 보여 준다.
// 숫자는 서버 문안 그대로다 (화면에서 만들지 않는다). 업체용 문안이 null이면(❔·계산 안 함·규칙 미검증) 그 영역을 숨긴다.
import { useEffect, useRef, useState } from 'react'
import { fetchGuide } from '../api'
import { APP_TEXT, GUIDE_TEXT } from '../texts'
import type { ApplianceInput, Guide, GymInput, LaundryInput, ScreenItem } from '../types'
import { CopyBlock } from './CopyBlock'
import { NextStepsPanel } from './NextStepsPanel'

interface Props {
  item: ScreenItem
  input: GymInput | LaundryInput | ApplianceInput
  surveyUrl: string | null
  /** 응답을 받으면 부른다 (결과 카드 팝업 result_cards가 다음 행동을 보여 줄 때만 넘긴다). 화면에는 영향이 없다 */
  onLoaded?: (input: GymInput | LaundryInput | ApplianceInput, guide: Guide | null) => void
}

type State = { kind: 'loading' } | { kind: 'ok'; guide: Guide } | { kind: 'error' }
/** 받은 응답과 그 응답을 요청한 입력. 입력이 바뀌면 새 응답이 올 때까지 '불러오는 중'으로 본다 */
type Loaded = { input: GymInput | LaundryInput | ApplianceInput; state: State }

export function GuidePanel({ item, input, surveyUrl, onLoaded }: Props) {
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  // 콜백이 바뀌어도 다시 요청하지 않도록 ref로 둔다
  const onLoadedRef = useRef(onLoaded)
  useEffect(() => {
    onLoadedRef.current = onLoaded
  })

  useEffect(() => {
    let alive = true
    fetchGuide(item, input).then((outcome) => {
      if (!alive) return
      setLoaded({ input, state: outcome.kind === 'ok' ? { kind: 'ok', guide: outcome.data } : { kind: 'error' } })
      onLoadedRef.current?.(input, outcome.kind === 'ok' ? outcome.data : null)
    })
    return () => {
      alive = false
    }
  }, [item, input])

  const state: State = loaded && loaded.input === input ? loaded.state : { kind: 'loading' }
  // 다음 행동(next_steps)이 있으면 그 안의 채널에 1372가 있으므로 아래 1372 한 줄을 다시 쓰지 않는다
  const mentions1372 =
    state.kind === 'ok' &&
    (state.guide.next_steps !== undefined || state.guide.explanation.some((line) => line.includes('1372')))

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
          {state.guide.next_steps && <NextStepsPanel data={state.guide.next_steps} />}
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
