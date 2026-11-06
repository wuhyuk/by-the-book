// 화면 문구. [스펙]은 docs/MVP_SPEC.md 원문 그대로, [초안]은 승인 대기
// (docs/sources/vs2_pending_approval.md). 사유·안내·고지 문구는 서버 응답(display)을 쓰고 여기 두지 않는다.

// [스펙] 10절: 첫 화면 지원 업종 안내
export const SUPPORTED_INDUSTRIES = '지원 업종: 헬스·피트니스업, 요가·필라테스업'

// [스펙] 5.5 PT_ONLY_QUESTION 입력 질문
export const PT_ONLY_QUESTION = 'PT만 계약하셨나요?'

// [스펙] 5.5 POSTPONEMENT_INPUT 입력 안내
export const POSTPONEMENT_INPUT_HINT = '이용을 연기했다면 종료일에는 연장된 종료일을 입력해 주세요.'

// [스펙] 5.1 withdrawal_cleared 확인 항목과 풀이
export const WITHDRAWAL_CLEARED_LABEL = '청약철회 대상이 아니거나 기간이 지났음을 확인했습니다'
export const WITHDRAWAL_CLEARED_HINT =
  '계약서 수령일부터 7일·14일이 지났거나, 권유 없이 직접 매장을 찾아가 일시불로 계약한 경우 (법적 판정이 아닌 참고 풀이입니다). 전화·길거리 권유나 무료 체험 안내를 받고 방문해 계약했다면 1372에 확인해 주세요.'

// [스펙] 5.1 used_sessions 설명 (요가·필라테스 표준약관 제9조 ②)
export const USED_SESSIONS_YOGA_HINT =
  '요가·필라테스 표준약관을 쓴 계약이면 받지 않은 보강수업도 이용 횟수에 넣습니다.'

// [스펙] 5.3 결과 묶음 표시, 5.3 계산 과정 첫 줄의 시나리오 표기
export const BASIS_LABEL = { period: '일수 기준', session: '횟수 기준' } as const
export const SCENARIO_LABEL = { A: '실제 부담액 기준(A)', B: '정상가 기준(B)' } as const
export const REFUND_KIND_LABEL = { minimum: '최소 환급액', computed: '환급액' } as const

// [초안] 입력 항목 라벨 (누락 항목·입력 오류 표시에도 쓴다)
export const FIELD_LABEL: Record<string, string> = {
  industry: '업종',
  termination_cause: '해지 사유',
  contract_type: '계약 방식',
  refund_basis: '계약할 때 정한 환급 기준',
  academy_law_applies: '학원법 시행령 적용 계약',
  is_withdrawal: '청약철회로 해지',
  withdrawal_cleared: '청약철회 확인',
  total_contract_amount: '총계약대금',
  paid_amount: '지급한 금액',
  start_date: '시작일',
  end_date: '종료일',
  notice_date: '해지 의사가 업체에 도달한 날',
  total_sessions: '계약상 총 횟수',
  used_sessions: '이용한 횟수',
  add_on_value: '부가상품(사은품 등) 가액',
  add_on_returned: '부가상품 반환',
  returned_add_on_value: '반환한 부가상품의 가치',
  deposit: '보증금',
  has_refund_limit_clause: '중도 해지 시 환급 제한·위약금 조항',
  list_price: '정상가 (할인 전 총액)',
  contract_penalty: '계약서상 위약금',
  provider_offer: '업체가 제시한 환급액',
  had_postponement: '이용 연기(일시정지)',
  is_pt_only: 'PT만 계약',
}

// [초안] 입력 오류 종류
export const ISSUE_TYPE_LABEL: Record<string, string> = {
  missing: '필수 항목입니다',
  json_invalid: '요청 형식이 맞지 않습니다',
  int_type: '숫자로 입력해 주세요',
  int_parsing: '숫자로 입력해 주세요',
  date_parsing: '날짜 형식이 맞지 않습니다',
  date_type: '날짜 형식이 맞지 않습니다',
  literal_error: '선택지 중에서 골라 주세요',
  extra_forbidden: '알 수 없는 항목입니다',
}

// [초안] 입력 검사 문구
export const INPUT_ERROR = {
  required: '선택하거나 입력해 주세요',
  won: '0 이상의 정수(원 단위)로 입력해 주세요',
  count: '0 이상의 정수(회)로 입력해 주세요',
  body: '요청 전체',
}

// [초안] 결과 화면 고정 라벨
export const RESULT_TEXT = {
  notCalculated: '계산하지 않았습니다.',
  missingTitle: '빠진 항목',
  otherFlags: (n: number) => `다른 확인 사항 ${n}개`,
  bNotCalculated: '계산하지 않음',
  depositRefund: '보증금 환급 (환급액과 별도)',
  steps: '계산 과정',
  notices: '안내',
  citations: '근거 조항',
  ruleSource: '기준',
  consultTitle: '상담 창구',
}
