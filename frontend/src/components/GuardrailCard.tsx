// 승패·법적 효력 질문 결과 (❔ 판단 불가). 문구와 배지는 서버 응답(규칙 코드)을 그대로 보여 준다.
import { RESULT_TEXT } from '../texts'
import type { GuardrailDisplay } from '../types'

export function GuardrailCard({ data }: { data: GuardrailDisplay }) {
  return (
    <section className="result" aria-live="polite" data-testid="guardrail">
      <div className="result-head">
        <span className="badge badge-unknown" data-testid="badge">
          {data.badge}
        </span>
        <p className="screen-line" data-testid="screen-line">
          {data.screen_line.text}
        </p>
      </div>
      <div className="consult" data-testid="consult">
        <h3>{RESULT_TEXT.consultTitle}</h3>
        <p>{data.consult.message}</p>
        <ul>
          {data.consult.channels.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </div>
    </section>
  )
}
