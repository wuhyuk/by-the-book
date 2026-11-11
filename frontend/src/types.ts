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

// /api/analyze 응답 (backend/api/analyze.py, llm/extraction.py).
// fields는 근거 구절을 코드가 확인한 값만 있다. 폼을 미리 채우는 데만 쓰고, 계산은 /api/calculate가 한다.
export type ExtractedValue = string | number | boolean

export interface AnalyzeResult {
  fields: Partial<Record<keyof GymInput, ExtractedValue>>
  evidence: Partial<Record<keyof GymInput, string>>
  unverified: string[]
  missing: string[]
  confirm: string[]
  judgment_requested: boolean
}

export interface GuardrailDisplay {
  badge: string
  screen_line: DisplayLine
  consult: { message: string; channels: string[] }
}

export interface AnalyzeResponse {
  status: 'extracted' | 'guardrail'
  pii_masked: boolean
  extraction: AnalyzeResult | null
  guardrail: GuardrailDisplay | null
}

// ---- 세탁 (VS4, backend/rules/laundry.py·laundry_display.py, MVP_SPEC 12절) ----
// 화면은 응답 값을 그대로 표시만 한다. 사용일수·배상비율·금액을 새로 계산하지 않는다.

export type Item = 'gym' | 'laundry'

export interface LaundryInput {
  judgment_requested: boolean
  service_type: string
  damage_type: 'defect' | 'loss' | 'other'
  manufacturing_cause_claimed: TriState
  item_key: string | null
  item_unlisted: boolean
  variant_key: string | null
  purchase_price: number | null
  purchase_date: string | null
  request_date: string | null
  proof_available: TriState
  laundry_fee: number | null
  set_type: 'none' | 'top_bottom' | 'top_mid_bottom' | 'hanbok'
  set_part: 'top' | 'mid' | 'bottom' | 'whole' | null
  attachment_only: TriState
  special_agreement: TriState
  customer_partial_fault: TriState
  wants_damaged_item: TriState
  no_issue_confirmation: TriState
  uncollected: TriState
  receipt_issued: TriState
  provider_offer: number | null
}

export interface LaundryResult {
  badge: string
  calculated: boolean
  method: 'ratio' | 'fallback' | null
  use_days: number | null
  life_years: number | null
  ratio_percent: number | null
  band_min_days: number | null
  band_max_days: number | null
  amount: number | null
  fallback_amount: number | null
  sensitivity_min: number | null
  sensitivity_max: number | null
  sensitivity_causes: ('use_days' | 'rounding')[]
  sensitivity_ratio_alt: number | null
  steps: Step[]
  flags: string[]
  missing: string[]
  notices: string[]
  citations: string[]
}

export interface LaundryDisplay {
  badge: string
  screen_line: DisplayLine | null
  other_flags: DisplayLine[]
  notices: DisplayLine[]
  citations: CitationCard[]
  rule_source: {
    name: string
    notice_number: string
    annex: string
    url: string
    effective_date: string
    last_amended: string
    retrieved_at: string
  }
  disclaimer: string
  consult: { message: string; channels: string[] } | null
}

export interface LaundryCalculateResponse {
  result: LaundryResult
  display: LaundryDisplay
}

export interface LaundryItemOption {
  key: string
  label: string
  examples: string | null
  variant_by: 'use' | 'material' | null
  variants: DisplayLine[]
}

export interface LaundryAnalyzeResult {
  fields: Partial<Record<keyof LaundryInput, ExtractedValue>>
  evidence: Partial<Record<keyof LaundryInput, string>>
  unverified: string[]
  missing: string[]
  confirm: string[]
  judgment_requested: boolean
}

// GET /api/config (backend/api/config.py). analyze_enabled = 스위치 켜짐 그리고 하루 상한 미도달.
export interface AppConfig {
  analyze_enabled: boolean
  survey_url: string | null
}

// POST /api/guide (backend/guide/). 서버가 다시 계산한 결과로 만든 문안. 화면은 그대로 보여 준다.
export interface Guide {
  explanation: string[]
  company_message: string | null
  citations: CitationCard[]
}

// 품목 화면 공통 props (Root가 /api/config로 정한다)
export interface ScreenProps {
  /** null이면 문장 분석 패널을 보여 준다. 문자열이면 패널 대신 이 안내를 보여 준다 */
  analyzeOff: string | null
  /** 분석 요청이 ANALYZE_DISABLED·ANALYZE_DAILY_LIMIT로 끝나면 부른다 (서버 안내 문구) */
  onAnalyzeUnavailable: (message: string) => void
  surveyUrl: string | null
}
