import type { Item } from './types'

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

// 문장 입력·분석 (VS3). privacy는 [결정 2026-11-08 사용자] 문구 그대로, 나머지는 [초안] 승인 대기
// (docs/sources/vs3_report.md 3절 C).
export const ANALYZE_TEXT = {
  title: '상황을 문장으로 입력',
  label: '상황 설명',
  placeholder:
    '예: 헬스장 1년권을 2026-01-01부터 2026-12-31까지 120만원에 결제했는데, 이사 때문에 2026-03-31에 해지하겠다고 했어요.',
  // [사용자 지시 2026-11-12] 입력창 아래 상시 고지
  privacy:
    '입력한 문장은 외부 AI(Google Gemini 무료 등급)로 전송되며 Google이 서비스 개선에 사용할 수 있습니다. 이름·주소·전화번호·계좌번호는 넣지 마세요.',
  calcNote: '입력한 문장은 저장하지 않습니다. 금액은 AI가 아니라 고시의 계산식대로 코드가 계산합니다.',
  button: '문장에서 항목 찾기',
  analyzing: '찾는 중…',
  masked: '개인정보로 보이는 부분을 가린 뒤 분석했습니다.',
  filled: (n: number) =>
    n > 0
      ? `문장에서 찾은 항목 ${n}개를 아래 폼의 빈칸에 채웠습니다. 값이 맞는지 확인한 뒤 '기준 금액 확인'을 눌러 주세요.`
      : '문장에서 새로 채울 항목을 찾지 못했습니다. 아래 폼에 직접 입력해 주세요.',
  askTitle: '더 필요한 정보',
  unverifiedTitle: '문장에서 확인하지 못한 값',
  conflictTitle: '입력한 값과 문장이 다른 항목',
  confirmTitle: '확인이 필요한 항목',
  confirmNote: '문장에서 이렇게 보입니다. 이 값이면 기준 금액을 계산하지 않으니 맞는지 확인해 주세요.',
  missingNote: '문장에서 찾지 못했습니다. 입력해 주세요.',
  unverifiedNote: '문장의 값을 확인하지 못해 비워 두었습니다. 직접 입력해 주세요.',
  conflictNote: (value: string) => `문장에서는 ${value}(으)로 보입니다. 입력한 값을 그대로 두었습니다.`,
  evidence: (t: string) => `문장: “${t}”`,
  or: '또는 아래 폼에 직접 입력할 수 있습니다.',
}

// [초안] 문장 값 표시용 선택지 이름 (폼의 선택지 문구와 같은 뜻)
export const VALUE_LABEL: Record<string, Record<string, string>> = {
  industry: { fitness: '헬스·피트니스', yoga_pilates: '요가·필라테스', other: '그 외 업종' },
  contract_type: { period: '기간제', session: '횟수제' },
  refund_basis: { period: '기간 기준', session: '횟수 기준', unknown: '모름' },
  termination_cause: { consumer: '내 사정', business: '업체 사정', force_majeure: '불가항력', unknown: '모름' },
}

// ---- 세탁 (VS4, MVP_SPEC 12절) ----
// [초안] 승인 대기 (docs/sources/vs4_report.md 3절). 사유·안내·고지 문구는 서버 응답(display)을 쓴다.

export const ITEM_TAB_LABEL = { gym: '헬스장·요가·필라테스', laundry: '세탁' } as const

export const LAUNDRY_TEXT = {
  lead: '세탁소에 맡긴 옷이 손상되거나 분실됐을 때 소비자분쟁해결기준의 배상 기준 금액을 고시의 계산식대로 보여 드립니다.',
  supported: '지원 범위: 세탁소에 맡긴 세탁물의 손상·분실 (무인세탁소, 세탁 지연, 세트 일부·부속물 손상은 아직 지원하지 않습니다)',
  placeholder:
    '예: 2025년 11월 1일에 40만원에 산 겨울 정장을 2026년 10월 1일에 세탁소에 맡겼는데 색이 변했어요. 영수증은 있어요.',
  itemsLoadError: '품목 목록을 불러오지 못했습니다. 백엔드가 실행 중인지 확인해 주세요.',
  submit: '기준 금액 확인',
  submitting: '확인 중…',
  amountTitle: '기준 금액',
  ratioLabel: '물품구입가격 × 배상비율',
  fallbackLabel: '세탁요금 × 20',
  fallbackTitle: '입증이 어려울 때의 기준 금액 (세탁요금 × 20)',
  range: (min: string, max: string) => `고시에 없는 결정에 따라 ${min}~${max}`,
  lookup: (life: number, ratio: number) => `내용연수 ${life}년 · 배상비율 ${ratio}%`,
  daysText: (n: number) => `사용일수 ${n.toLocaleString('ko-KR')}일`,
  unlistedOption: '표에 맞는 품목이 없음',
  proofHint: '인수증·영수증·결제 내역 등으로 품명·구입가격·구입일을 정할 수 있으면 "예"입니다.',
  dateHint: '사용일수는 구입일 다음 날부터 세탁을 맡긴 날까지 셉니다 (계산은 서버가 합니다).',
  selectionNote: '문장에서 고른 표의 품목(소재·용도)입니다. 맞는지 확인해 주세요.',
  routeNote: '문장에서 이렇게 보입니다. 이 값이면 세탁요금의 20배로 계산하니 맞는지 확인해 주세요.',
}

export const LAUNDRY_FIELD_LABEL: Record<string, string> = {
  service_type: '어디에 맡겼나요',
  damage_type: '피해 종류',
  proof_available: '품명·구입가격·구입일을 입증할 수 있나요',
  item_key: '세탁물 품목 (평균 내용연수표)',
  item_unlisted: '표에 없는 품목',
  variant_key: '소재·용도',
  purchase_price: '구입가격',
  purchase_date: '구입일',
  request_date: '세탁을 맡긴 날',
  laundry_fee: '세탁요금',
  set_type: '세트 의류',
  set_part: '손상·분실된 부분',
  receipt_issued: '세탁소에서 인수증을 받았나요',
  manufacturing_cause_claimed: '업체가 원단·제조 불량을 주장하나요',
  attachment_only: '털·칼라·모자 같은 탈부착 부속물만 손상됐나요',
  special_agreement: '배상에 관한 특약이 있나요',
  customer_partial_fault: '업체가 고객에게도 책임이 있다고 하나요',
  wants_damaged_item: '손상된 세탁물을 돌려받고 싶나요',
  no_issue_confirmation: '찾을 때 "이상 없음" 확인서(인수증 서명 포함)를 써 줬나요',
  uncollected: '업체가 오래 찾아가지 않았다고 하나요 (통지 후 30일, 완성 예정일 다음날부터 3개월)',
  provider_offer: '업체가 제시한 배상액',
}

export const LAUNDRY_VALUE_LABEL: Record<string, Record<string, string>> = {
  service_type: { laundry_shop: '세탁소에 맡김', self_laundromat: '무인세탁소(셀프빨래방)', other: '그 외' },
  damage_type: { defect: '하자 (탈색·변색·손상 등)', loss: '분실·소실', other: '그 외 (세탁 지연 등)' },
  set_type: { none: '세트 아님', top_bottom: '상·하의 한 벌', top_mid_bottom: '상·중·하의 한 벌', hanbok: '한복 치마저고리·바지저고리' },
  set_part: { whole: '한 벌 전체', top: '상의', mid: '중의', bottom: '하의' },
}

// [초안 2026-11-12] 첫 화면 예시 문장 (가상 사례, 누르면 입력창에 채운다)
export const EXAMPLES: Record<Item, readonly string[]> = {
  gym: [
    '헬스장 6개월권을 2026년 3월 1일부터 2026년 8월 31일까지 쓰기로 하고 60만원을 결제했어요. 2026년 5월 10일에 해지하겠다고 매장에 말했어요.',
    '필라테스 30회권을 90만원에 결제했고 2026년 4월 1일부터 9월 30일까지 쓸 수 있어요. 8회 수업을 들은 뒤 2026년 6월 1일에 그만두겠다고 했는데 업체가 30만원만 돌려준대요.',
  ],
  laundry: [
    '세탁소에 맡긴 겨울 코트가 줄어들어서 왔어요. 2025년 12월 1일에 30만원에 샀고 2026년 10월 5일에 세탁을 맡겼어요.',
    '세탁소에서 셔츠를 잃어버렸대요. 언제 얼마에 샀는지 증명할 자료가 없고 세탁요금은 5천원이었어요.',
  ],
}

// [초안 2026-11-12] 화면 공통 문구
export const APP_TEXT = {
  examplesTitle: '예시 문장 (누르면 입력창에 채워집니다)',
  disclaimer:
    '이 서비스의 결과는 참고용이며 법률 자문이 아닙니다. 고시는 분쟁 해결의 기준이며, 실제 환급·배상 여부와 금액을 확정하지 않습니다.',
  // 분석 꺼짐(/api/config)일 때 패널 자리 안내 (서버 ANALYZE_DISABLED 문구와 같음)
  analyzeOff: '문장 분석은 지금 쓸 수 없습니다. 아래 입력 폼으로 입력해 주세요',
  survey: '만족도 설문 참여(약 3분)',
  consult1372: '도움이 더 필요하면 1372 소비자상담센터(국번 없이 1372)에 문의해 주세요.',
} as const

// [초안 2026-11-12] 설명·업체용 문안 영역
export const GUIDE_TEXT = {
  title: '설명과 업체용 문안',
  explanationTitle: '설명',
  companyTitle: '업체에 보낼 문안 (사실·기준 요약)',
  copyExplanation: '설명 복사',
  copyCompany: '업체용 문안 복사',
  copied: '복사했습니다.',
  copyFailed: '자동 복사를 하지 못했습니다. 아래 글을 길게 눌러(또는 전체 선택해) 직접 복사해 주세요.',
  loading: '문안을 만드는 중…',
  loadFailed: '설명 문안을 불러오지 못했습니다. 위 결과 카드는 그대로 볼 수 있습니다.',
} as const
