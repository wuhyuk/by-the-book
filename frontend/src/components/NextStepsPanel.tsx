// 다음 행동 (POST /api/guide의 next_steps, 기능 플래그 next_steps). 문구·항목·채널은 서버 응답 그대로 보여 준다.
// 체크 표시는 이 화면에만 두고 서버·브라우저 저장소에 저장하지 않는다 (사용자 입력 비저장 원칙).
import { channelView } from '../nextSteps'
import { NEXT_STEPS_TEXT } from '../texts'
import type { NextSteps } from '../types'

export function NextStepsPanel({ data }: { data: NextSteps }) {
  return (
    <details className="next-steps" data-testid="next-steps">
      <summary>{data.title}</summary>
      {data.checklist.length > 0 && (
        <div className="next-steps-section" data-testid="next-steps-checklist">
          <h4>{data.checklist_title}</h4>
          <ul className="checklist">
            {data.checklist.map((item) => (
              <li key={item.text}>
                <label>
                  <input type="checkbox" />
                  <span>{item.text}</span>
                </label>{' '}
                <span className={item.basis === 'official' ? 'basis-tag basis-official' : 'basis-tag'}>
                  {item.basis_label}
                </span>
              </li>
            ))}
          </ul>
          {data.checklist_note && <p className="hint">{data.checklist_note}</p>}
          <p className="hint">{NEXT_STEPS_TEXT.checkNote}</p>
        </div>
      )}
      <div className="next-steps-section" data-testid="next-steps-channels">
        <h4>{data.channels_title}</h4>
        <ul className="channels">
          {data.channels.map((c) => {
            const v = channelView(c)
            return (
              <li key={c.id} data-testid={`channel-${c.id}`}>
                <strong>{c.name}</strong>
                {v.telHref && (
                  <>
                    {' · '}
                    <a href={v.telHref}>{v.phoneText}</a>
                  </>
                )}
                <p>{v.how}</p>
                <p className="hint">
                  {v.url && (
                    <>
                      <a href={v.url} target="_blank" rel="noopener noreferrer">
                        {NEXT_STEPS_TEXT.website}
                      </a>
                      {' · '}
                    </>
                  )}
                  {v.status}
                </p>
              </li>
            )
          })}
        </ul>
      </div>
      <p className="disclaimer">{data.disclaimer}</p>
    </details>
  )
}
