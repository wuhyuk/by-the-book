// 백엔드 /api/calculate 요청·응답 타입 (backend/rules/gym.py, gym_display.py, api/calculate.py).
// 화면은 이 응답 값을 그대로 표시만 한다. 금액을 새로 계산하지 않는다.
import type { HistoryAccess } from './history/storage.ts'

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
  offer_gap?: OfferGap // 기능 플래그 offer_gap이 켜져 있을 때만 (MVP_SPEC 14.1)
}

// 업체 제시액과 기준 금액의 차액 (서버 엔진이 정수로 계산, 화면은 표시만)
export interface OfferGap {
  offer: number
  reference_min: number
  reference_max: number
  gap_to_min: number
  gap_to_max: number
  direction: 'below_min' | 'within' | 'above_max' | 'equal'
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
  offer_gap_text?: string // 제시액 차액 한 줄 (offer_gap 켜짐일 때만)
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
  /** 기능 플래그 date_year_infer: 연도 없는 날짜를 코드 규칙으로 보완한 항목 → 그 연도. 꺼져 있으면 키가 없다 */
  year_inferred?: Record<string, number>
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
  clauses?: ClauseSuggestions // 기능 플래그 rag가 켜져 있을 때만 (MVP_SPEC 15.2)
}

// 자동 검색한 조항 후보 (규칙 JSON에 저장된 값만, 금액 계산에 쓰지 않음)
export interface ClauseItem {
  clause_id: string
  title: string
  source_name: string
  retrieved_at: string
  verified: boolean
  user_checked: boolean | null
  excerpt: string
}

export interface ClauseSuggestions {
  candidates: ClauseItem[]
  selected: ClauseItem[]
}

// GET /api/sources/{id} (MVP_SPEC 14.3)
export interface ClauseSource {
  id: string
  label: string
  text: string
  source: { name: string; url: string; retrieved_at: string }
  retrieved_at: string
  verified: boolean
  user_checked: boolean | null
  rule_ids: string[]
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
  // R2 (set_partial 켜짐일 때만 보낸다. 폼으로만 받는다)
  hanbok_kind?: 'chima_jeogori' | 'baji_jeogori' | null
  damaged_parts?: ('top' | 'mid' | 'bottom')[] | null
  set_partial_request?: TriState
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
  sensitivity_causes: ('use_days' | 'rounding' | 'set_partial_damage')[]
  sensitivity_ratio_alt: number | null
  steps: Step[]
  flags: string[]
  missing: string[]
  notices: string[]
  citations: string[]
  // R2 출력 (꺼져 있거나 Set이 아니면 null)
  set_type: string | null
  hanbok_kind: string | null
  damaged_parts: string[] | null
  set_share_percent: number | null
  set_base_raw: string | null
  offer_gap?: OfferGap
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
  offer_gap_text?: string // 제시액 차액 한 줄 (offer_gap 켜짐일 때만)
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
  set_types?: string[] // 이 품목 행에서 고를 수 있는 Set 유형 (서버가 준다)
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
  enabled_features?: string[] // 켜 둔 복원 기능 (ENABLED_FEATURES). set_partial = 세탁 세트 일부 손상
}

// POST /api/guide (backend/guide/). 서버가 다시 계산한 결과로 만든 문안. 화면은 그대로 보여 준다.
export interface Guide {
  explanation: string[]
  company_message: string | null
  citations: CitationCard[]
  next_steps?: NextSteps // 기능 플래그 next_steps가 켜져 있을 때만 (MVP_SPEC 14.2)
}

// 다음 행동 (서버 고정 텍스트). 체크 표시는 화면에만 두고 저장하지 않는다.
export interface NextStepsChecklistItem {
  text: string
  basis: 'official' | 'general'
  basis_label: string
  source_url: string | null
  checked_on: string | null
}

export interface NextStepsChannel {
  id: string
  name: string
  phone: string | null
  url: string | null
  how: string | null
  source_urls: string[]
  checked_on: string | null
  status: 'confirmed' | 'needs_check'
}

export interface NextSteps {
  title: string
  checklist_title: string
  checklist: NextStepsChecklistItem[]
  checklist_note: string | null
  channels_title: string
  channels: NextStepsChannel[]
  disclaimer: string
}

// 품목 화면 공통 props (Root가 /api/config로 정한다)
export interface ScreenProps {
  /** null이면 문장 분석 패널을 보여 준다. 문자열이면 패널 대신 이 안내를 보여 준다 */
  analyzeOff: string | null
  /** 분석 요청이 ANALYZE_DISABLED·ANALYZE_DAILY_LIMIT로 끝나면 부른다 (서버 안내 문구) */
  onAnalyzeUnavailable: (message: string) => void
  surveyUrl: string | null
  /** 켜 둔 복원 기능 (/api/config enabled_features). 세탁 화면만 쓴다 */
  features: readonly string[]
  /** 내 기록 (local_history). null이면 꺼짐(저장 버튼 없음), storage가 null이면 이 브라우저에서 저장 불가 */
  history?: HistoryAccess | null
}

// ---- 가전 P2 (MVP_SPEC 13절, ENABLED_FEATURES=appliance일 때만) ----
// 문장 분석 대상이 아니라 Item(분석·예시용)에는 넣지 않는다. 탭·문안은 ScreenItem을 쓴다.
export type ScreenItem = Item | 'appliance'

export interface ApplianceInput {
  judgment_requested: boolean
  item_key: string | null
  item_unlisted: boolean
  purchase_price: number | null
  purchase_date: string | null
  request_date: string | null
  manufacture_date: string | null
  parts_unavailable: TriState
  certificate_confirmed: TriState
  certificate_warranty_months: number | null
  certificate_parts_years: number | null
  provider_offer: number | null
}

export interface ApplianceResult {
  badge: string
  calculated: boolean
  item_key: string | null
  row_id: string | null
  warranty_months: number | null
  life_months: number | null
  used_months: number | null
  used_months_full: number | null
  partial_month: boolean | null
  amount: number | null
  sensitivity_min: number | null
  sensitivity_max: number | null
  sensitivity_causes: ('partial_month' | 'rounding' | 'cap')[]
  steps: Step[]
  flags: string[]
  missing: string[]
  notices: string[]
  citations: string[]
  offer_gap?: OfferGap
}

export interface ApplianceCalculateResponse {
  result: ApplianceResult
  display: LaundryDisplay // 같은 모양 (badge, screen_line, other_flags, notices, citations, rule_source, disclaimer, consult)
}

export interface ApplianceItemOption {
  key: string
  label: string
}
