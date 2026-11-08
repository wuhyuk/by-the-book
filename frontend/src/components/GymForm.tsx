import { createContext, useContext, type FormEvent, type ReactNode } from 'react'
import { visibility, type FormState, type TriChoice } from '../formState'
import {
  ANALYZE_TEXT,
  FIELD_LABEL,
  POSTPONEMENT_INPUT_HINT,
  PT_ONLY_QUESTION,
  USED_SESSIONS_YOGA_HINT,
  WITHDRAWAL_CLEARED_HINT,
  WITHDRAWAL_CLEARED_LABEL,
} from '../texts'

interface Props {
  form: FormState
  onChange: (next: FormState) => void
  onSubmit: () => void
  submitting: boolean
  fieldErrors: Record<string, string>
  /** 문장 분석 뒤 되묻기 안내 (항목 이름 → 문구) */
  notes?: Record<string, string>
  /** 문장 분석에서 값의 근거가 된 구절 (항목 이름 → 구절) */
  evidence?: Record<string, string>
}

const Extras = createContext<{ notes: Record<string, string>; evidence: Record<string, string> }>({
  notes: {},
  evidence: {},
})

function ExtraLines({ name }: { name: string }) {
  const { notes, evidence } = useContext(Extras)
  return (
    <>
      {evidence[name] && <p className="evidence">{ANALYZE_TEXT.evidence(evidence[name])}</p>}
      {notes[name] && (
        <p className="ask-note" data-testid={`ask-${name}`}>
          {notes[name]}
        </p>
      )}
    </>
  )
}

type Key = keyof FormState

function Field(props: {
  name: string
  label?: string
  hint?: ReactNode
  error?: string
  children: ReactNode
}) {
  const label = props.label ?? FIELD_LABEL[props.name]
  const { notes } = useContext(Extras)
  const cls = props.error ? 'field field-error' : notes[props.name] ? 'field field-ask' : 'field'
  return (
    <div className={cls}>
      <label htmlFor={props.name}>{label}</label>
      {props.children}
      {props.hint && <p className="hint">{props.hint}</p>}
      <ExtraLines name={props.name} />
      {props.error && (
        <p className="error" role="alert">
          {props.error}
        </p>
      )}
    </div>
  )
}

export function GymForm({ form, onChange, onSubmit, submitting, fieldErrors, notes = {}, evidence = {} }: Props) {
  const v = visibility(form)
  const set = <K extends Key>(key: K, value: FormState[K]) => onChange({ ...form, [key]: value })
  const yoga = form.industry === 'yoga_pilates'
  const sessionOnly = !v.periodFields && v.sessionFields

  const text = (name: Key, opts: { optional?: boolean; hint?: ReactNode; label?: string } = {}) => (
    <Field
      name={name}
      label={opts.label ? opts.label : undefined}
      hint={opts.hint}
      error={fieldErrors[name]}
    >
      <input
        id={name}
        name={name}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        placeholder={opts.optional ? '선택' : ''}
        value={form[name] as string}
        onChange={(e) => set(name, e.target.value as FormState[typeof name])}
      />
    </Field>
  )

  const date = (name: 'start_date' | 'end_date' | 'notice_date', label: string, hint?: ReactNode) => (
    <Field name={name} label={label} hint={hint} error={fieldErrors[name]}>
      <input
        id={name}
        name={name}
        type="date"
        autoComplete="off"
        value={form[name]}
        onChange={(e) => set(name, e.target.value)}
      />
    </Field>
  )

  const tri = (name: 'has_refund_limit_clause' | 'had_postponement' | 'is_pt_only', label?: string) => (
    <Field name={name} label={label} error={fieldErrors[name]}>
      <select id={name} name={name} value={form[name]} onChange={(e) => set(name, e.target.value as TriChoice)}>
        <option value="unknown">모름</option>
        <option value="yes">예</option>
        <option value="no">아니오</option>
      </select>
    </Field>
  )

  const check = (name: 'academy_law_applies' | 'is_withdrawal' | 'add_on_returned', label?: string) => (
    <div className="field field-check">
      <input
        id={name}
        name={name}
        type="checkbox"
        checked={form[name]}
        onChange={(e) => set(name, e.target.checked)}
      />
      <label htmlFor={name}>{label ?? FIELD_LABEL[name]}</label>
      <ExtraLines name={name} />
    </div>
  )

  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit()
  }

  return (
    <Extras.Provider value={{ notes, evidence }}>
      <form className="gym-form" onSubmit={submit} autoComplete="off" noValidate>
        <fieldset>
          <legend>계약 정보</legend>
          <Field name="industry" error={fieldErrors.industry}>
            <select id="industry" name="industry" value={form.industry} onChange={(e) => set('industry', e.target.value)}>
              {form.industry === '' && <option value="">선택해 주세요</option>}
              <option value="fitness">헬스·피트니스</option>
              <option value="yoga_pilates">요가·필라테스</option>
              <option value="other">그 외 (수영장, 골프연습장 등)</option>
            </select>
          </Field>
          <Field name="contract_type" error={fieldErrors.contract_type}>
            <select
              id="contract_type"
              name="contract_type"
              value={form.contract_type}
              onChange={(e) => set('contract_type', e.target.value as FormState['contract_type'])}
            >
              <option value="">선택해 주세요</option>
              <option value="period">기간제 (예: 3개월, 1년)</option>
              <option value="session">횟수제 (예: 20회)</option>
            </select>
          </Field>
          {v.refundBasis && (
            <Field name="refund_basis" error={fieldErrors.refund_basis}>
              <select
                id="refund_basis"
                name="refund_basis"
                value={form.refund_basis}
                onChange={(e) => set('refund_basis', e.target.value as FormState['refund_basis'])}
              >
                <option value="">선택해 주세요</option>
                <option value="period">기간 기준</option>
                <option value="session">횟수 기준</option>
                <option value="unknown">모름</option>
              </select>
            </Field>
          )}
          {v.ptQuestion && tri('is_pt_only', PT_ONLY_QUESTION)}
          <Field name="termination_cause" error={fieldErrors.termination_cause}>
            <select
              id="termination_cause"
              name="termination_cause"
              value={form.termination_cause}
              onChange={(e) => set('termination_cause', e.target.value as FormState['termination_cause'])}
            >
              <option value="">선택해 주세요</option>
              <option value="consumer">내 사정 (단순 변심, 이사 등)</option>
              <option value="business">업체 사정 (폐업, 운영 중단 등)</option>
              <option value="force_majeure">천재지변 등 불가항력</option>
              <option value="unknown">모름</option>
            </select>
          </Field>
          {tri('has_refund_limit_clause')}
          {check('academy_law_applies')}
          {check('is_withdrawal')}
          <div className="field field-check">
            <input
              id="withdrawal_cleared"
              name="withdrawal_cleared"
              type="checkbox"
              checked={form.withdrawal_cleared}
              onChange={(e) => set('withdrawal_cleared', e.target.checked)}
            />
            <label htmlFor="withdrawal_cleared">{WITHDRAWAL_CLEARED_LABEL}</label>
            <p className="hint">{WITHDRAWAL_CLEARED_HINT}</p>
            <ExtraLines name="withdrawal_cleared" />
          </div>
        </fieldset>

        <fieldset>
          <legend>금액 (원)</legend>
          {text('total_contract_amount', { hint: '가입비·입회금 포함, 보증금 제외' })}
          {text('paid_amount')}
          {text('list_price', { optional: true })}
          {text('contract_penalty', { optional: true })}
          {text('provider_offer', { optional: true })}
          {text('deposit', { optional: true })}
          {text('add_on_value', { optional: true })}
          {check('add_on_returned')}
          {v.returnedAddOn && text('returned_add_on_value')}
        </fieldset>

        <fieldset>
          <legend>기간·횟수</legend>
          {tri('had_postponement')}
          {date('start_date', sessionOnly ? '유효기간 시작일 (선택)' : '이용 시작일')}
          {date(
            'end_date',
            sessionOnly ? '유효기간 종료일 (선택)' : '이용 종료일',
            v.postponementHint ? POSTPONEMENT_INPUT_HINT : undefined,
          )}
          {date('notice_date', FIELD_LABEL.notice_date)}
          {v.sessionFields && text('total_sessions')}
          {v.sessionFields && text('used_sessions', { hint: yoga ? USED_SESSIONS_YOGA_HINT : undefined })}
        </fieldset>

        <button type="submit" disabled={submitting}>
          {submitting ? '계산 중…' : '기준 금액 확인'}
        </button>
      </form>
    </Extras.Provider>
  )
}
