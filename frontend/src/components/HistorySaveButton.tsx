// "이 결과 저장" (기능 플래그 local_history, MVP_SPEC 18절). 결과 카드 바로 아래에 둔다.
// 이 브라우저 localStorage에만 쓰고 서버로 보내지 않는다. 저장 값은 /api/calculate 응답 그대로다.
import { useState } from 'react'
import { addItem, type HistoryAccess, type HistoryDomain } from '../history/storage'
import { saveMessage } from '../history/view'
import { HISTORY_TEXT } from '../texts'

interface Props {
  history: HistoryAccess
  domain: HistoryDomain
  /** /api/calculate에 보낸 입력 */
  inputs: object
  /** /api/calculate 응답 */
  result: object
  /** 문장 입력으로 폼을 채운 경우의 문장 */
  sentence?: string | null
  /** 'dialog'는 결과 카드 팝업의 닫기 버튼 옆 (result_cards). 저장 경로·문구는 인라인과 같다 */
  placement?: 'inline' | 'dialog'
}

export function HistorySaveButton({ history, domain, inputs, result, sentence, placement = 'inline' }: Props) {
  // 메시지는 그 메시지를 만든 결과에만 보인다 (새 계산 결과에는 이전 메시지를 보이지 않는다)
  const [message, setMessage] = useState<{ for: object; text: string } | null>(null)
  const storage = history.storage
  const text = message && message.for === result ? message.text : ''

  if (storage === null) {
    // 팝업에서는 버튼을 숨긴다 (저장소를 쓸 수 없다는 안내는 인라인에만 둔다)
    if (placement === 'dialog') return null
    return (
      <p className="history-save hint" data-testid="history-unavailable">
        {HISTORY_TEXT.unavailable}
      </p>
    )
  }

  const save = () => {
    const outcome = addItem(storage, { domain, inputs, result, sentence })
    setMessage({ for: result, text: saveMessage(outcome) })
  }

  if (placement === 'dialog') {
    return (
      <div className="rc-save" data-testid="rc-save">
        <button type="button" className="copy-button rc-save-button" onClick={save} data-testid="rc-save-button">
          {HISTORY_TEXT.save}
        </button>
        <p className="rc-save-status" role="status" aria-live="polite" data-testid="rc-save-status">
          {text}
        </p>
      </div>
    )
  }

  return (
    <div className="history-save" data-testid="history-save">
      <button type="button" className="copy-button" onClick={save} data-testid="history-save-button">
        {HISTORY_TEXT.save}
      </button>
      <p className="history-status" role="status" aria-live="polite" data-testid="history-save-status">
        {text}
      </p>
    </div>
  )
}
