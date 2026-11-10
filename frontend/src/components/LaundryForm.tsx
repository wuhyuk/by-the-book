// 세탁 입력 폼 (MVP_SPEC 12.1). 품목·소재·용도는 서버가 준 표 행 이름 그대로 고른다 (내용연수 숫자 없음).
import type { FormEvent, ReactNode } from 'react'
import type { TriChoice } from '../formState'
import { laundryVisibility, UNLISTED, type LaundryForm as Form } from '../laundryForm'
import { ANALYZE_TEXT, LAUNDRY_FIELD_LABEL, LAUNDRY_TEXT, LAUNDRY_VALUE_LABEL } from '../texts'
import type { LaundryItemOption } from '../types'

interface Props {
  form: Form
  items: LaundryItemOption[]
  onChange: (next: Form) => void
  onSubmit: () => void
  submitting: boolean
  fieldErrors: Record<string, string>
  notes: Record<string, string>
  evidence: Record<string, string>
}

type Key = keyof Form

export function LaundryForm({ form, items, onChange, onSubmit, submitting, fieldErrors, notes, evidence }: Props) {
  const v = laundryVisibility(form, items)
  const set = <K extends Key>(key: K, value: Form[K]) => {
    const next = { ...form, [key]: value }
    if (key === 'item_key') next.variant_key = '' // 품목을 바꾸면 소재·용도를 다시 고른다
    if (key === 'set_type') next.set_part = ''
    onChange(next)
  }

  const field = (name: Key, control: ReactNode, hint?: ReactNode) => {
    const cls = fieldErrors[name] ? 'field field-error' : notes[name] ? 'field field-ask' : 'field'
    return (
      <div className={cls}>
        <label htmlFor={`l-${name}`}>{LAUNDRY_FIELD_LABEL[name]}</label>
        {control}
        {hint && <p className="hint">{hint}</p>}
        {evidence[name] && <p className="evidence">{ANALYZE_TEXT.evidence(evidence[name])}</p>}
        {notes[name] && (
          <p className="ask-note" data-testid={`ask-${name}`}>
            {notes[name]}
          </p>
        )}
        {fieldErrors[name] && (
          <p className="error" role="alert">
            {fieldErrors[name]}
          </p>
        )}
      </div>
    )
  }

  const select = (name: Key, options: [string, string][], placeholder?: string) =>
    field(
      name,
      <select
        id={`l-${name}`}
        name={name}
        value={form[name]}
        onChange={(e) => set(name, e.target.value as Form[typeof name])}
      >
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>,
    )

  const labeled = (name: string) => Object.entries(LAUNDRY_VALUE_LABEL[name]) as [string, string][]

  const tri = (name: Key, hint?: ReactNode) =>
    field(
      name,
      <select
        id={`l-${name}`}
        name={name}
        value={form[name]}
        onChange={(e) => set(name, e.target.value as TriChoice as Form[typeof name])}
      >
        <option value="unknown">모름</option>
        <option value="yes">예</option>
        <option value="no">아니오</option>
      </select>,
      hint,
    )

  const money = (name: 'purchase_price' | 'laundry_fee' | 'provider_offer', optional = false) =>
    field(
      name,
      <input
        id={`l-${name}`}
        name={name}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        placeholder={optional ? '선택' : ''}
        value={form[name]}
        onChange={(e) => set(name, e.target.value)}
      />,
    )

  const date = (name: 'purchase_date' | 'request_date', hint?: ReactNode) =>
    field(
      name,
      <input
        id={`l-${name}`}
        name={name}
        type="date"
        autoComplete="off"
        value={form[name]}
        onChange={(e) => set(name, e.target.value)}
      />,
      hint,
    )

  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit()
  }

  const setParts: [string, string][] = labeled('set_part').filter(
    ([k]) => k !== 'mid' || form.set_type === 'top_mid_bottom',
  )

  return (
    <form className="gym-form laundry-form" onSubmit={submit} autoComplete="off" noValidate data-testid="laundry-form">
      <fieldset>
        <legend>피해 정보</legend>
        {select('service_type', labeled('service_type'), '선택해 주세요')}
        {select('damage_type', labeled('damage_type'), '선택해 주세요')}
        {tri('proof_available', LAUNDRY_TEXT.proofHint)}
      </fieldset>
      {v.ratioFields && (
        <fieldset>
          <legend>세탁물</legend>
          {select(
            'item_key',
            [
              ...items.map((i): [string, string] => [i.key, i.examples ? `${i.label} (${i.examples})` : i.label]),
              [UNLISTED, LAUNDRY_TEXT.unlistedOption],
            ],
            '선택해 주세요',
          )}
          {v.variant &&
            select(
              'variant_key',
              v.variant.variants.map((x): [string, string] => [x.code, x.text]),
              '선택해 주세요',
            )}
          {money('purchase_price')}
          {date('purchase_date')}
          {date('request_date', LAUNDRY_TEXT.dateHint)}
        </fieldset>
      )}
      {v.feeField && (
        <fieldset>
          <legend>입증이 어려울 때</legend>
          {money('laundry_fee')}
        </fieldset>
      )}
      <fieldset>
        <legend>세트·부속물</legend>
        {select('set_type', labeled('set_type'))}
        {v.setPart && select('set_part', setParts, '선택해 주세요')}
        {tri('attachment_only')}
      </fieldset>
      <fieldset>
        <legend>업체 주장·약정 (선택)</legend>
        {tri('receipt_issued')}
        {tri('manufacturing_cause_claimed')}
        {tri('special_agreement')}
        {tri('customer_partial_fault')}
        {tri('wants_damaged_item')}
        {tri('no_issue_confirmation')}
        {tri('uncollected')}
        {money('provider_offer', true)}
      </fieldset>
      <button type="submit" disabled={submitting}>
        {submitting ? LAUNDRY_TEXT.submitting : LAUNDRY_TEXT.submit}
      </button>
    </form>
  )
}
