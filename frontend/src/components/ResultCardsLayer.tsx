// 결과 카드 팝업 (기능 플래그 result_cards, 기본 꺼짐). 인라인 결과 카드는 그대로 두고 그 위에 겹쳐 보이는 층이다.
// 새 계산 결과가 오면 열리고, 닫으면 이 자리에 "결과 카드 다시 열기" 버튼이 남는다. 세 품목 화면이 같이 쓴다.
// 카드 내용은 src/results/cards.ts가 응답 값을 골라 담은 것 그대로다 (금액을 새로 계산하지 않는다).
import { useEffect, useId, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { channelView } from '../nextSteps'
import { buildResultCards, type CardSource, type ResultCardData } from '../results/cards'
import { NEXT_STEPS_TEXT, RESULT_CARDS_TEXT, RESULT_TEXT } from '../texts'
import type { NextSteps } from '../types'

interface Props<T> {
  /** 인라인 결과 카드에 넘기는 것과 같은 계산 응답. 새 객체가 오면 팝업이 열린다 */
  response: T | null
  toSource: (response: T) => CardSource
  /** 설명 응답(/api/guide)의 다음 행동. 아직 없으면 null */
  nextSteps?: NextSteps | null
  /** 닫기 버튼 앞에 둘 "이 결과 저장" (local_history 켜짐 + 저장소 사용 가능일 때만 화면이 넘긴다) */
  saveAction?: ReactNode
}

const FOCUSABLE = 'a[href], button:not([disabled]), summary, input:not([disabled]), [tabindex]:not([tabindex="-1"])'

function won(n: number): string {
  return `${n.toLocaleString('ko-KR')}원`
}

const CARD_TITLE: Record<ResultCardData['kind'], string> = {
  summary: RESULT_CARDS_TEXT.summary,
  steps: RESULT_CARDS_TEXT.steps,
  citations: RESULT_CARDS_TEXT.citations,
  next: RESULT_CARDS_TEXT.next,
}

function CardBody({ card }: { card: ResultCardData }) {
  switch (card.kind) {
    case 'summary':
      return (
        <>
          {card.screenLine && <p className="rc-line">{card.screenLine}</p>}
          {card.guide && <p>{card.guide}</p>}
          {card.missing.length > 0 && (
            <p>
              {RESULT_TEXT.missingTitle}: {card.missing.join(', ')}
            </p>
          )}
          {card.offerGap && <p className="offer-gap">{card.offerGap}</p>}
          {card.otherFlags.length > 0 && (
            <>
              <h4>{RESULT_TEXT.otherFlags(card.otherFlags.length)}</h4>
              <ul>
                {card.otherFlags.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </>
          )}
          {card.notices.length > 0 && (
            <>
              <h4>{RESULT_TEXT.notices}</h4>
              <ul>
                {card.notices.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </>
          )}
        </>
      )
    case 'steps':
      return (
        <ol className="rc-steps">
          {card.steps.map((s, i) => (
            <li key={i}>
              <strong>{s.label}</strong>
              <span className="rc-formula">{s.formula}</span>
              {s.amount !== null && <span className="rc-step-amount">{won(s.amount)}</span>}
            </li>
          ))}
        </ol>
      )
    case 'citations':
      return (
        <>
          {card.citations.map((c) => (
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
        </>
      )
    case 'next':
      return (
        <>
          {card.consult && (
            <>
              <h4>{RESULT_TEXT.consultTitle}</h4>
              <p>{card.consult.message}</p>
              {/* 다음 행동이 있으면 창구는 그 목록으로 한 번만 보인다 (인라인 카드와 같은 규칙) */}
              {!card.nextSteps && (
                <ul>
                  {card.consult.channels.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              )}
            </>
          )}
          {card.nextSteps && card.nextSteps.checklist.length > 0 && (
            <>
              <h4>{card.nextSteps.checklist_title}</h4>
              <ul>
                {card.nextSteps.checklist.map((item) => (
                  <li key={item.text}>
                    {item.text}{' '}
                    <span className={item.basis === 'official' ? 'basis-tag basis-official' : 'basis-tag'}>
                      {item.basis_label}
                    </span>
                  </li>
                ))}
              </ul>
              {card.nextSteps.checklist_note && <p className="hint">{card.nextSteps.checklist_note}</p>}
            </>
          )}
          {card.nextSteps && (
            <>
              <h4>{card.nextSteps.channels_title}</h4>
              <ul className="channels">
                {card.nextSteps.channels.map((c) => {
                  const v = channelView(c)
                  return (
                    <li key={c.id}>
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
            </>
          )}
        </>
      )
  }
}

export function ResultCardsLayer<T extends object>({ response, toSource, nextSteps = null, saveAction = null }: Props<T>) {
  // 사용자가 닫은 응답. 새 응답이 오면 이 값과 달라져 다시 열린다
  const [closedFor, setClosedFor] = useState<T | null>(null)
  const [pos, setPos] = useState<{ for: T | null; index: number }>({ for: null, index: 0 })
  const dialogRef = useRef<HTMLDivElement>(null)
  const reopenRef = useRef<HTMLButtonElement>(null)
  const returnTo = useRef<HTMLElement | null>(null)
  const closeRef = useRef<() => void>(() => {})
  const titleId = useId()

  const open = response !== null && closedFor !== response
  const close = () => setClosedFor(response)
  useEffect(() => {
    closeRef.current = close
  })

  // 열린 동안: 팝업으로 포커스 이동, Esc로 닫기, 배경 스크롤 잠금 (닫으면 원래 값으로)
  useEffect(() => {
    if (!open) return
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const body = document.body
    const prevOverflow = body.style.overflow
    body.style.overflow = 'hidden'
    dialogRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        closeRef.current()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      body.style.overflow = prevOverflow
      returnTo.current = opener
    }
  }, [open])

  // 닫힌 뒤: 팝업을 연 요소로 포커스를 돌린다. 그 요소가 없어졌거나 누를 수 없으면 "다시 열기" 버튼으로
  useEffect(() => {
    if (open || returnTo.current === null) return
    const el = returnTo.current
    returnTo.current = null
    const usable = el.isConnected && el !== document.body && !(el instanceof HTMLButtonElement && el.disabled)
    if (usable) el.focus()
    else reopenRef.current?.focus()
  }, [open])

  if (response === null) return null
  if (!open) {
    return (
      <div className="rc-reopen">
        <button
          type="button"
          className="copy-button"
          ref={reopenRef}
          onClick={() => setClosedFor(null)}
          data-testid="rc-reopen"
        >
          {RESULT_CARDS_TEXT.reopen}
        </button>
      </div>
    )
  }

  const source = toSource(response)
  const cards = buildResultCards(source, nextSteps)
  const last = Math.max(cards.length - 1, 0)
  const index = Math.min(pos.for === response ? pos.index : 0, last)
  const go = (i: number) => setPos({ for: response, index: i })
  const card = cards[index] ?? null
  const h = source.header

  // Tab 순환 (포커스 트랩)
  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'Tab' || !dialogRef.current) return
    const nodes = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
      (el) => el.getClientRects().length > 0,
    )
    if (nodes.length === 0) {
      e.preventDefault()
      return
    }
    const first = nodes[0]
    const lastNode = nodes[nodes.length - 1]
    const active = document.activeElement
    if (e.shiftKey && (active === first || active === dialogRef.current)) {
      e.preventDefault()
      lastNode.focus()
    } else if (!e.shiftKey && active === lastNode) {
      e.preventDefault()
      first.focus()
    }
  }

  return createPortal(
    <div
      className="rc-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) close()
      }}
      data-testid="rc-backdrop"
    >
      <div
        className="rc-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        ref={dialogRef}
        onKeyDown={onKeyDown}
        data-testid="rc-dialog"
      >
        <div className="rc-head">
          <div className={saveAction ? 'rc-titlebar rc-titlebar-save' : 'rc-titlebar'}>
            <h2 id={titleId}>{RESULT_CARDS_TEXT.dialogTitle}</h2>
            {saveAction}
            <button type="button" className="copy-button rc-close" onClick={close} data-testid="rc-close">
              {RESULT_CARDS_TEXT.close}
            </button>
          </div>
          <div className="rc-status">
            <span className={`badge badge-${h.tone}`} data-testid="rc-badge">
              {h.badge}
            </span>
            {h.notice && <p className="rc-notice">{h.notice}</p>}
            {h.status === 'not_calculated' && <p className="rc-notice">{RESULT_TEXT.notCalculated}</p>}
          </div>
          {h.amounts.length > 0 && (
            <dl className="rc-amounts" data-testid="rc-amounts">
              {h.amounts.map((a) => (
                <div key={a.label} className="rc-amount">
                  <dt>{a.label}</dt>
                  {a.value === null ? (
                    <dd className="rc-amount-na">{RESULT_TEXT.bNotCalculated}</dd>
                  ) : (
                    <dd>{won(a.value)}</dd>
                  )}
                </div>
              ))}
            </dl>
          )}
          {h.hints.map((t) => (
            <p key={t} className="hint">
              {t}
            </p>
          ))}
          {h.deposit !== null && (
            <p className="hint">
              {RESULT_TEXT.depositRefund}: {won(h.deposit)}
            </p>
          )}
        </div>
        {card && (
          <div className="rc-card" key={`${card.kind}-${index}`} data-testid={`rc-card-${card.kind}`}>
            <h3>{CARD_TITLE[card.kind]}</h3>
            <CardBody card={card} />
          </div>
        )}
        {cards.length > 1 && (
          <div className="rc-nav">
            {/* 끝에서도 disabled로 바꾸지 않는다 (누르던 버튼이 꺼지면 포커스가 팝업 밖으로 빠진다) */}
            <button
              type="button"
              className="copy-button"
              onClick={() => index > 0 && go(index - 1)}
              aria-disabled={index === 0}
              data-testid="rc-prev"
            >
              {RESULT_CARDS_TEXT.prev}
            </button>
            <span className="rc-position" aria-live="polite" data-testid="rc-position">
              {RESULT_CARDS_TEXT.position(index + 1, cards.length)}
            </span>
            <button
              type="button"
              className="copy-button"
              onClick={() => index < last && go(index + 1)}
              aria-disabled={index === last}
              data-testid="rc-next"
            >
              {RESULT_CARDS_TEXT.nextCard}
            </button>
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}
