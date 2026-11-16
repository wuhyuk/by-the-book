// 내 기록 패널 (기능 플래그 local_history, MVP_SPEC 18절). 열 때마다 저장소를 다시 읽는다 (Root가 열 때 새로 그린다).
// 저장된 결과는 읽기 전용으로 결과 카드에 그대로 넣는다. 문장은 텍스트로만 보여 준다 (HTML로 해석하지 않음).
// 다른 브라우저 탭과 동기화하지 않는다. 서버로 보내지 않는다.
import { Component, useEffect, useRef, useState, type ReactNode } from 'react'
import { clearAll, deleteItem, loadItems, type HistoryItem, type StorageLike } from '../history/storage'
import { amountSummary, baseDateText, domainLabel, formatKst, isRenderable, kstDate, savedBadge } from '../history/view'
import { HISTORY_TEXT } from '../texts'
import type { ApplianceCalculateResponse, CalculateResponse, LaundryCalculateResponse } from '../types'
import { ApplianceResultCard } from './ApplianceResultCard'
import { CopyBlock } from './CopyBlock'
import { LaundryResultCard } from './LaundryResultCard'
import { ResultCard } from './ResultCard'

function badgeClass(badge: string): string {
  if (badge.startsWith('✅')) return 'badge badge-ok'
  if (badge.startsWith('⚠️')) return 'badge badge-warn'
  if (badge.startsWith('❔')) return 'badge badge-unknown'
  return 'badge badge-review'
}

/** 결과 카드를 그리다 예외가 나면(예전 모양의 저장 값) 요약으로 대신한다 */
class CardBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

function Summary({ item }: { item: HistoryItem }) {
  const badge = savedBadge(item.result)
  return (
    <p className="history-summary">
      {badge && <span className={badgeClass(badge)}>{badge}</span>} <span>{amountSummary(item.domain, item.result)}</span>
    </p>
  )
}

function SavedResult({ item }: { item: HistoryItem }) {
  const fallback = (
    <div className="result" data-testid="history-summary-card">
      <p className="hint">{HISTORY_TEXT.notRenderable}</p>
      <Summary item={item} />
    </div>
  )
  if (!isRenderable(item.domain, item.result)) return fallback
  const card =
    item.domain === 'gym' ? (
      <ResultCard data={item.result as unknown as CalculateResponse} />
    ) : item.domain === 'laundry' ? (
      <LaundryResultCard data={item.result as unknown as LaundryCalculateResponse} />
    ) : (
      <ApplianceResultCard data={item.result as unknown as ApplianceCalculateResponse} />
    )
  return <CardBoundary fallback={fallback}>{card}</CardBoundary>
}

export function HistoryPanel({ storage, onClose }: { storage: StorageLike; onClose: () => void }) {
  const [items, setItems] = useState<HistoryItem[]>(() => loadItems(storage))
  const [openId, setOpenId] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [status, setStatus] = useState('')
  const headingRef = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  const remove = (id: string) => {
    const ok = deleteItem(storage, id)
    setItems(loadItems(storage))
    if (openId === id) setOpenId(null)
    setStatus(ok ? HISTORY_TEXT.removed : HISTORY_TEXT.removeFailed)
  }

  const clear = () => {
    const ok = clearAll(storage)
    setItems(loadItems(storage))
    setOpenId(null)
    setConfirming(false)
    setStatus(ok ? HISTORY_TEXT.cleared : HISTORY_TEXT.removeFailed)
  }

  return (
    <section className="history-panel" aria-labelledby="history-title" data-testid="history-panel">
      <div className="history-head">
        <h2 id="history-title" tabIndex={-1} ref={headingRef}>
          {HISTORY_TEXT.title} <span className="hint">{HISTORY_TEXT.count(items.length)}</span>
        </h2>
        <button type="button" className="copy-button" onClick={onClose} data-testid="history-close">
          {HISTORY_TEXT.close}
        </button>
      </div>
      <p className="hint" data-testid="history-notice">
        {HISTORY_TEXT.notice}
      </p>
      <p className="history-status" role="status" aria-live="polite" data-testid="history-status">
        {status}
      </p>
      {items.length === 0 ? (
        <p data-testid="history-empty">{HISTORY_TEXT.empty}</p>
      ) : (
        <ul className="history-list" data-testid="history-list">
          {items.map((item) => {
            const when = formatKst(item.savedAt)
            const open = openId === item.id
            const base = baseDateText(item.result)
            return (
              <li key={item.id} className="history-row" data-testid="history-row">
                <div className="history-row-head">
                  <p className="history-meta">
                    <span>{when}</span> · <span>{domainLabel(item.domain)}</span>
                  </p>
                  <Summary item={item} />
                  <div className="history-actions">
                    <button
                      type="button"
                      className="copy-button"
                      aria-expanded={open}
                      aria-label={open ? undefined : HISTORY_TEXT.viewLabel(when)}
                      onClick={() => setOpenId(open ? null : item.id)}
                      data-testid="history-view"
                    >
                      {open ? HISTORY_TEXT.hide : HISTORY_TEXT.view}
                    </button>
                    <button
                      type="button"
                      className="copy-button"
                      aria-label={HISTORY_TEXT.removeLabel(when)}
                      onClick={() => remove(item.id)}
                      data-testid="history-delete"
                    >
                      {HISTORY_TEXT.remove}
                    </button>
                  </div>
                </div>
                {open && (
                  <div className="history-detail" data-testid="history-detail">
                    <p className="history-saved-heading">
                      <strong>{HISTORY_TEXT.savedHeading(kstDate(item.savedAt))}</strong>
                      {base && <span className="hint"> · {base}</span>}
                    </p>
                    <p className="hint">{HISTORY_TEXT.staleNote}</p>
                    {item.sentence && (
                      <CopyBlock
                        title={HISTORY_TEXT.sentenceTitle}
                        buttonLabel={HISTORY_TEXT.copySentence}
                        lines={item.sentence.split('\n')}
                        testId="history-sentence"
                      />
                    )}
                    <SavedResult item={item} />
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {items.length > 0 &&
        (confirming ? (
          <div className="history-confirm" data-testid="history-confirm">
            <p>{HISTORY_TEXT.clearConfirm}</p>
            <button type="button" className="copy-button" onClick={clear} data-testid="history-clear-yes">
              {HISTORY_TEXT.clearYes}
            </button>{' '}
            <button type="button" className="copy-button" onClick={() => setConfirming(false)}>
              {HISTORY_TEXT.cancel}
            </button>
          </div>
        ) : (
          <button type="button" className="copy-button" onClick={() => setConfirming(true)} data-testid="history-clear">
            {HISTORY_TEXT.clearAll}
          </button>
        ))}
    </section>
  )
}
