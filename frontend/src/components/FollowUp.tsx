// 문장 분석 뒤 되묻기 안내 (VS3). 서버가 준 missing·unverified 항목 이름만 보여 준다.
import { ANALYZE_TEXT, FIELD_LABEL } from '../texts'

interface Props {
  filledCount: number
  missing: string[]
  unverified: string[]
  conflicts: string[]
  confirm: string[]
  piiMasked: boolean
  /** 항목 이름표 (기본: 헬스장 항목) */
  labels?: Record<string, string>
  /** 확인이 필요한 항목에 덧붙일 완성된 문장 (세탁 세트 단서, 2026-11-16). 없으면 지금과 같다 */
  extraConfirm?: string[]
}

export function FollowUp({
  filledCount,
  missing,
  unverified,
  conflicts,
  confirm,
  piiMasked,
  labels = FIELD_LABEL,
  extraConfirm = [],
}: Props) {
  const label = (f: string) => labels[f] ?? f
  const confirmLines = [...confirm.map(label), ...extraConfirm]
  return (
    <div className="follow-up" role="status" data-testid="follow-up">
      <p>{ANALYZE_TEXT.filled(filledCount)}</p>
      {piiMasked && <p className="hint">{ANALYZE_TEXT.masked}</p>}
      {missing.length > 0 && (
        <p data-testid="ask-missing">
          <strong>{ANALYZE_TEXT.askTitle}:</strong> {missing.map(label).join(', ')}
        </p>
      )}
      {confirmLines.length > 0 && (
        <p data-testid="ask-confirm">
          <strong>{ANALYZE_TEXT.confirmTitle}:</strong> {confirmLines.join(', ')}
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
