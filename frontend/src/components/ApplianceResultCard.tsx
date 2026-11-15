// 가전 결과 카드. 모든 값은 서버 응답(result, display)을 그대로 표시한다. 금액·개월을 새로 계산하지 않는다.
import { APPLIANCE_FIELD_LABEL, APPLIANCE_TEXT, RESULT_TEXT } from '../texts'
import type { ApplianceCalculateResponse } from '../types'

function won(n: number): string {
  return `${n.toLocaleString('ko-KR')}원`
}

function badgeClass(badge: string): string {
  if (badge.startsWith('✅')) return 'badge badge-ok'
  if (badge.startsWith('⚠️')) return 'badge badge-warn'
  if (badge.startsWith('❔')) return 'badge badge-unknown'
  return 'badge badge-review'
}

export function ApplianceResultCard({
  data,
  channelsBelow = false,
}: {
  data: ApplianceCalculateResponse
  channelsBelow?: boolean
}) {
  const { result, display } = data
  const ranged =
    result.sensitivity_min !== null &&
    result.sensitivity_max !== null &&
    result.sensitivity_min !== result.sensitivity_max

  return (
    <section className="result" aria-live="polite" data-testid="appliance-result">
      <div className="result-head">
        <span className={badgeClass(display.badge)} data-testid="badge">
          {display.badge}
        </span>
        {display.screen_line && (
          <p className="screen-line" data-testid="screen-line">
            {display.screen_line.text}
          </p>
        )}
      </div>

      {display.other_flags.length > 0 && (
        <details className="other-flags">
          <summary>{RESULT_TEXT.otherFlags(display.other_flags.length)}</summary>
          <ul>
            {display.other_flags.map((f) => (
              <li key={f.code}>{f.text}</li>
            ))}
          </ul>
        </details>
      )}

      {display.consult && (
        <div className="consult" data-testid="consult">
          <h3>{RESULT_TEXT.consultTitle}</h3>
          <p>{display.consult.message}</p>
          {/* 다음 행동(next_steps)이 켜져 있으면 창구 목록은 아래 '다음 행동'에 한 번만 보인다 */}
          {!channelsBelow && (
            <ul>
              {display.consult.channels.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {!result.calculated && (
        <div className="not-calculated">
          <p>{RESULT_TEXT.notCalculated}</p>
          {result.missing.length > 0 && (
            <p>
              {RESULT_TEXT.missingTitle}: {result.missing.map((m) => APPLIANCE_FIELD_LABEL[m] ?? m).join(', ')}
            </p>
          )}
        </div>
      )}

      {result.calculated && result.amount !== null && (
        <div className="amounts" data-testid="amounts">
          <div className="basis">
            <h3>{APPLIANCE_TEXT.amountTitle}</h3>
            <dl>
              <dt>{APPLIANCE_TEXT.amountLabel}</dt>
              <dd data-testid="appliance-amount">{won(result.amount)}</dd>
            </dl>
            {result.life_months !== null && result.used_months !== null && (
              <p className="hint">{APPLIANCE_TEXT.lookup(result.life_months, result.used_months)}</p>
            )}
            {ranged && (
              <p className="hint" data-testid="appliance-range">
                {APPLIANCE_TEXT.range(won(result.sensitivity_min!), won(result.sensitivity_max!))}
              </p>
            )}
          </div>
        </div>
      )}

      {display.offer_gap_text && (
        <p className="offer-gap" data-testid="offer-gap">
          {display.offer_gap_text}
        </p>
      )}

      {result.steps.length > 0 && (
        <details className="steps" open>
          <summary>{RESULT_TEXT.steps}</summary>
          <table>
            <tbody>
              {result.steps.map((s, i) => (
                <tr key={i}>
                  <th scope="row">{s.label}</th>
                  <td>{s.formula}</td>
                  <td className="num">{s.amount === null ? '' : won(s.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}

      {display.notices.length > 0 && (
        <div className="notices">
          <h3>{RESULT_TEXT.notices}</h3>
          <ul>
            {display.notices.map((n) => (
              <li key={n.code}>{n.text}</li>
            ))}
          </ul>
        </div>
      )}

      {display.citations.length > 0 && (
        <div className="citations">
          <h3>{RESULT_TEXT.citations}</h3>
          {display.citations.map((c) => (
            <details key={c.id} className="citation">
              <summary>
                {c.label} · {c.source.name}
              </summary>
              <blockquote>{c.text}</blockquote>
              <p className="source">
                출처:{' '}
                <a href={c.source.url} target="_blank" rel="noreferrer noopener">
                  {c.source.name}
                </a>{' '}
                (확인일 {c.source.retrieved_at})
              </p>
            </details>
          ))}
        </div>
      )}

      <footer className="rule-source">
        <p>
          {RESULT_TEXT.ruleSource}: {display.rule_source.name} {display.rule_source.annex} (
          {display.rule_source.notice_number}, 시행 {display.rule_source.effective_date}, 확인일{' '}
          {display.rule_source.retrieved_at})
        </p>
        <p className="disclaimer" data-testid="disclaimer">
          {display.disclaimer}
        </p>
      </footer>
    </section>
  )
}
