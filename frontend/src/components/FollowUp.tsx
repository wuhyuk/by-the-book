// 문장 분석 뒤 되묻기 안내 (VS3). 서버가 준 missing·unverified 항목 이름만 보여 준다.
import { ANALYZE_TEXT, FIELD_LABEL } from '../texts'

interface Props {
  filledCount: number
  missing: string[]
  unverified: string[]
  conflicts: string[]
  confirm: string[]
  piiMasked: boolean
}

const label = (f: string) => FIELD_LABEL[f] ?? f

export function FollowUp({ filledCount, missing, unverified, conflicts, confirm, piiMasked }: Props) {
  return (
    <div className="follow-up" role="status" data-testid="follow-up">
      <p>{ANALYZE_TEXT.filled(filledCount)}</p>
      {piiMasked && <p className="hint">{ANALYZE_TEXT.masked}</p>}
      {missing.length > 0 && (
        <p data-testid="ask-missing">
          <strong>{ANALYZE_TEXT.askTitle}:</strong> {missing.map(label).join(', ')}
        </p>
      )}
      {confirm.length > 0 && (
        <p data-testid="ask-confirm">
          <strong>{ANALYZE_TEXT.confirmTitle}:</strong> {confirm.map(label).join(', ')}
        </p>
      )}
      {conflicts.length > 0 && (
        <p data-testid="ask-conflicts">
          <strong>{ANALYZE_TEXT.conflictTitle}:</strong> {conflicts.map(label).join(', ')}
        </p>
      )}
      {unverified.length > 0 && (
        <p data-testid="ask-unverified">
          <strong>{ANALYZE_TEXT.unverifiedTitle}:</strong> {unverified.map(label).join(', ')}
        </p>
      )}
    </div>
  )
}
