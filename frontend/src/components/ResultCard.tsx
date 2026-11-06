// 결과 카드. 모든 값은 서버 응답(result, display)을 그대로 표시한다. 금액을 새로 계산하지 않는다.
import type { Basis, CalculateResponse } from '../types'
import { BASIS_LABEL, FIELD_LABEL, REFUND_KIND_LABEL, RESULT_TEXT, SCENARIO_LABEL } from '../texts'

const BASIS_ORDER: Basis[] = ['period', 'session']

function won(n: number): string {
  return `${n.toLocaleString('ko-KR')}원`
}

function badgeClass(badge: string): string {
  if (badge.startsWith('✅')) return 'badge badge-ok'
  if (badge.startsWith('⚠️')) return 'badge badge-warn'
  if (badge.startsWith('❔')) return 'badge badge-unknown'
  return 'badge badge-review'
}

export function ResultCard({ data }: { data: CalculateResponse }) {
  const { result, display } = data
  const refundLabel = result.refund_kind ? REFUND_KIND_LABEL[result.refund_kind] : ''
  const bases = BASIS_ORDER.filter((b) => result.results[b] !== undefined)

  return (
    <section className="result" aria-live="polite" data-testid="result">
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

      {display.withdrawal_guide && <p className="guide">{display.withdrawal_guide}</p>}

      {display.consult && (
        <div className="consult" data-testid="consult">
          <h3>{RESULT_TEXT.consultTitle}</h3>
          <p>{display.consult.message}</p>
          <ul>
            {display.consult.channels.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}

      {!result.calculated && (
        <div className="not-calculated">
          <p>{RESULT_TEXT.notCalculated}</p>
          {result.missing.length > 0 && (
            <p>
              {RESULT_TEXT.missingTitle}: {result.missing.map((m) => FIELD_LABEL[m] ?? m).join(', ')}
            </p>
          )}
        </div>
      )}

      {result.calculated && (
        <div className="amounts" data-testid="amounts">
          {bases.map((b) => {
            const r = result.results[b]!
            return (
              <div className="basis" key={b} data-testid={`basis-${b}`}>
                <h3>{BASIS_LABEL[b]}</h3>
                <dl>
                  <dt>
                    {SCENARIO_LABEL.A} {refundLabel}
                  </dt>
                  <dd data-testid={`refund-${b}-A`}>{won(r.A.refund)}</dd>
                  <dt>
                    {SCENARIO_LABEL.B} {refundLabel}
                  </dt>
                  <dd data-testid={`refund-${b}-B`}>{r.B ? won(r.B.refund) : RESULT_TEXT.bNotCalculated}</dd>
                </dl>
              </div>
            )
          })}
          {result.deposit_refund > 0 && (
            <p className="deposit">
              {RESULT_TEXT.depositRefund}: {won(result.deposit_refund)}
            </p>
          )}
        </div>
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
          {RESULT_TEXT.ruleSource}: {display.rule_source.name} ({display.rule_source.notice_number}, 시행{' '}
          {display.rule_source.effective_date}, 확인일 {display.rule_source.retrieved_at})
        </p>
        <p className="disclaimer" data-testid="disclaimer">
          {display.disclaimer}
        </p>
      </footer>
    </section>
  )
}
