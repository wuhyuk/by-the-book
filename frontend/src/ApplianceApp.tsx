// 가전 화면 (MVP_SPEC 13절 P2, ENABLED_FEATURES=appliance일 때만 Root가 탭을 보인다).
// 폼 입력만 받는다 (문장 분석 없음). 상태는 useState로만 두고 입력값을 URL·localStorage·콘솔에 남기지 않는다.
import { type FormEvent, type ReactNode, useEffect, useState } from 'react'
import { calculateAppliance, fetchApplianceItems } from './api'
import { ApplianceResultCard } from './components/ApplianceResultCard'
import { GuidePanel } from './components/GuidePanel'
import {
  APPLIANCE_UNLISTED,
  buildApplianceInput,
  INITIAL_APPLIANCE_FORM,
  type ApplianceForm,
} from './applianceForm'
import type { TriChoice } from './formState'
import { APPLIANCE_FIELD_LABEL, APPLIANCE_TEXT, INPUT_ERROR, ISSUE_TYPE_LABEL } from './texts'
import type { ApplianceCalculateResponse, ApplianceInput, ApplianceItemOption } from './types'

type Key = keyof ApplianceForm

export function ApplianceApp({ surveyUrl, features }: { surveyUrl: string | null; features: readonly string[] }) {
  const [items, setItems] = useState<ApplianceItemOption[]>([])
  const [itemsError, setItemsError] = useState(false)
  const [form, setForm] = useState<ApplianceForm>(INITIAL_APPLIANCE_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [response, setResponse] = useState<ApplianceCalculateResponse | null>(null)
  const [calcInput, setCalcInput] = useState<ApplianceInput | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    fetchApplianceItems().then((data) => {
      if (!alive) return
      if (data) setItems(data)
      else setItemsError(true)
    })
    return () => {
      alive = false
    }
  }, [])

  const set = <K extends Key>(key: K, value: ApplianceForm[K]) => {
    setForm({ ...form, [key]: value })
    setResponse(null) // 입력을 바꾸면 이전 결과를 지운다
  }

  const field = (name: Key, control: ReactNode, hint?: string) => (
    <div className={fieldErrors[name] ? 'field field-error' : 'field'}>
      <label htmlFor={`a-${name}`}>{APPLIANCE_FIELD_LABEL[name]}</label>
      {control}
      {hint && <p className="hint">{hint}</p>}
      {fieldErrors[name] && (
        <p className="error" role="alert">
          {fieldErrors[name]}
        </p>
      )}
    </div>
  )

  const text = (name: Key, optional = false) =>
    field(
      name,
      <input
        id={`a-${name}`}
        name={name}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        placeholder={optional ? '선택' : ''}
        value={form[name]}
        onChange={(e) => set(name, e.target.value)}
      />,
    )

  const date = (name: Key, hint?: string) =>
    field(
      name,
      <input
        id={`a-${name}`}
        name={name}
        type="date"
        autoComplete="off"
        value={form[name]}
        onChange={(e) => set(name, e.target.value)}
      />,
      hint,
    )

  const tri = (name: 'parts_unavailable' | 'certificate_confirmed', hint?: string) =>
    field(
      name,
      <select
        id={`a-${name}`}
        name={name}
        value={form[name]}
        onChange={(e) => set(name, e.target.value as TriChoice)}
      >
        <option value="unknown">모름</option>
        <option value="yes">예</option>
        <option value="no">아니오</option>
      </select>,
      hint,
    )

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setFieldErrors({})
    const built = buildApplianceInput(form)
    if (!built.ok) {
      setFieldErrors(Object.fromEntries(built.invalidFields.map((f) => [f, INPUT_ERROR.won])))
      setResponse(null)
      return
    }
    setSubmitting(true)
    let outcome: Awaited<ReturnType<typeof calculateAppliance>>
    try {
      outcome = await calculateAppliance(built.input)
    } finally {
      setSubmitting(false)
    }
    if (outcome.kind === 'ok') {
      setCalcInput(built.input)
      setResponse(outcome.data)
      return
    }
    setResponse(null)
    if (outcome.kind === 'invalid') {
      const errs: Record<string, string> = {}
      for (const issue of outcome.issues) {
        const last = issue.loc.length > 1 ? String(issue.loc[issue.loc.length - 1]) : 'body'
        errs[last] = ISSUE_TYPE_LABEL[issue.type] ?? INPUT_ERROR.required
      }
      setFieldErrors(errs)
    }
    setError(outcome.message)
  }

  return (
    <main className="app">
      <header>
        <h1>기준대로</h1>
        <p className="lead" data-testid="appliance-lead">
          {APPLIANCE_TEXT.lead}
        </p>
      </header>
      {itemsError && (
        <p className="request-error" role="alert">
          {APPLIANCE_TEXT.itemsLoadError}
        </p>
      )}
      <div className="layout">
        <div>
          <form className="gym-form appliance-form" onSubmit={onSubmit} autoComplete="off" noValidate>
            <fieldset>
              <legend>제품</legend>
              {field(
                'item_key',
                <select
                  id="a-item_key"
                  name="item_key"
                  value={form.item_key}
                  onChange={(e) => set('item_key', e.target.value)}
                >
                  <option value="">선택해 주세요</option>
                  {items.map((i) => (
                    <option key={i.key} value={i.key}>
                      {i.label}
                    </option>
                  ))}
                  <option value={APPLIANCE_UNLISTED}>{APPLIANCE_TEXT.unlistedOption}</option>
                </select>,
              )}
              {text('purchase_price')}
              {date('purchase_date')}
              {date('request_date')}
              {date('manufacture_date', APPLIANCE_TEXT.manufactureHint)}
            </fieldset>
            <fieldset>
              <legend>수리·보증</legend>
              {tri('parts_unavailable')}
              {tri('certificate_confirmed', APPLIANCE_TEXT.certificateHint)}
              {text('certificate_warranty_months', true)}
              {text('certificate_parts_years', true)}
              {text('provider_offer', true)}
            </fieldset>
            <button type="submit" disabled={submitting}>
              {submitting ? APPLIANCE_TEXT.submitting : APPLIANCE_TEXT.submit}
            </button>
          </form>
        </div>
        <div className="output">
          {error && (
            <p className="request-error" role="alert">
              {error}
            </p>
          )}
          {response && <ApplianceResultCard data={response} channelsBelow={features.includes('next_steps')} />}
          {response && calcInput && <GuidePanel item="appliance" input={calcInput} surveyUrl={surveyUrl} />}
        </div>
      </div>
    </main>
  )
}
