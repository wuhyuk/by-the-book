// 백엔드 /api/calculate 요청·응답 타입 (backend/rules/gym.py, gym_display.py, api/calculate.py).
// 화면은 이 응답 값을 그대로 표시만 한다. 금액을 새로 계산하지 않는다.

export type TriState = boolean | null

export interface GymInput {
  judgment_requested: boolean
  industry: string
  academy_law_applies: boolean
  is_withdrawal: boolean
  withdrawal_cleared: TriState
  termination_cause: 'consumer' | 'business' | 'force_majeure' | 'unknown'
  contract_type: 'period' | 'session'
  refund_basis: 'period' | 'session' | 'unknown' | null
  total_contract_amount: number
  paid_amount: number
  start_date: string | null
  end_date: string | null
  notice_date: string | null
  total_sessions: number | null
  used_sessions: number | null
  add_on_value: number
  add_on_returned: boolean
  returned_add_on_value: number | null
  deposit: number
  has_refund_limit_clause: TriState
  list_price: number | null
  contract_penalty: number | null
  provider_offer: number | null
  had_postponement: TriState
  is_pt_only: TriState
}

export type Basis = 'period' | 'session'

export interface ScenarioResult {
  used_amount: number
  raw_refund: number
  refund: number
}

export interface BasisResult {
  elapsed: number
  units: number
  A: ScenarioResult
  B: ScenarioResult | null
}

export interface Step {
  label: string
  formula: string
  amount: number | null
}

export interface GymResult {
  badge: string
  calculated: boolean
  results: Partial<Record<Basis, BasisResult>>
  penalty: number | null
  penalty_cap: number | null
  refund_kind: 'minimum' | 'computed' | null
  deposit_refund: number
  contract_days: number | null
  steps: Step[]
  flags: string[]
  missing: string[]
  notices: string[]
  citations: string[]
}

export interface DisplayLine {
  code: string
  text: string
}

export interface CitationCard {
  id: string
  label: string
  text: string
  source: { name: string; url: string; retrieved_at: string }
}

export interface GymDisplay {
  badge: string
  screen_line: DisplayLine | null
  other_flags: DisplayLine[]
  notices: DisplayLine[]
  citations: CitationCard[]
  rule_source: {
    name: string
    notice_number: string
    url: string
    effective_date: string
    last_amended: string
    retrieved_at: string
  }
  disclaimer: string
  consult: { message: string; channels: string[] } | null
  withdrawal_guide: string | null
}

export interface CalculateResponse {
  result: GymResult
  display: GymDisplay
}

export interface ValidationIssue {
  loc: (string | number)[]
  type: string
}
