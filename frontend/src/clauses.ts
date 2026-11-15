// 조항 확인 상태 문구 (rag 영역, /api/sources). verified는 기계 대조라 "자동 대조"로만 쓰고,
// user_checked가 null이면 "조항 단위 사용자 대조 기록 없음"으로 쓴다 (2026-11-16 사용자 조건).
import { CLAUSE_TEXT } from './texts.ts'

export function clauseStatus(verified: boolean, userChecked: boolean | null): [string, string] {
  const machine = verified ? CLAUSE_TEXT.machinePassed : CLAUSE_TEXT.machineNotPassed
  const user =
    userChecked === null ? CLAUSE_TEXT.userNone : userChecked ? CLAUSE_TEXT.userChecked : CLAUSE_TEXT.userNotChecked
  return [machine, user]
}
