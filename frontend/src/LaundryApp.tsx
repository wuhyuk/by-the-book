// 세탁 화면 (VS4). 상태는 이 컴포넌트의 useState로만 둔다. 입력값을 URL·localStorage·콘솔에 남기지 않는다.
import { useEffect, useState } from 'react'
import { ANALYZE_UNAVAILABLE_CODES, analyze, calculateLaundry, fetchLaundryItems } from './api'
import { AnalyzePanel } from './components/AnalyzePanel'
import { FollowUp } from './components/FollowUp'
import { GuardrailCard } from './components/GuardrailCard'
import { GuidePanel } from './components/GuidePanel'
import { LaundryForm } from './components/LaundryForm'
import { LaundryResultCard } from './components/LaundryResultCard'
import {
  buildLaundryInput,
  INITIAL_LAUNDRY_FORM,
  laundryFollowUpFields,
  laundryFormKey,
  mergeLaundryExtraction,
  UNLISTED,
  type LaundryForm as Form,
} from './laundryForm'
import {
  ANALYZE_TEXT,
  INPUT_ERROR,
  ISSUE_TYPE_LABEL,
  LAUNDRY_FIELD_LABEL,
  LAUNDRY_TEXT,
  LAUNDRY_VALUE_LABEL,
  EXAMPLES,
} from './texts'
import type {
  GuardrailDisplay,
  LaundryAnalyzeResult,
  LaundryCalculateResponse,
  LaundryInput,
  LaundryItemOption,
  ScreenProps,
} from './types'

interface Analysis {
  filledCount: number
  missing: string[]
  unverified: string[]
  conflicts: string[]
  confirm: string[]
  piiMasked: boolean
}

const SELECTION = new Set(['item_key', 'variant_key', 'item_unlisted'])

function without(rec: Record<string, string>, form: Form, next: Form): Record<string, string> {
  const keys = Object.keys(rec).filter((k) => !(k in next) || next[k as keyof Form] === form[k as keyof Form])
  return Object.fromEntries(keys.map((k) => [k, rec[k]]))
}

export function LaundryApp({ analyzeOff, onAnalyzeUnavailable, surveyUrl }: ScreenProps) {
  // 마지막으로 계산에 보낸 입력 (/api/guide에 그대로 다시 보낸다)
  const [calcInput, setCalcInput] = useState<LaundryInput | null>(null)
  const [items, setItems] = useState<LaundryItemOption[]>([])
  const [itemsError, setItemsError] = useState(false)
  const [form, setForm] = useState<Form>(INITIAL_LAUNDRY_FORM)
  const [touched, setTouched] = useState<ReadonlySet<string>>(new Set())
  const [submitting, setSubmitting] = useState(false)
  const [response, setResponse] = useState<LaundryCalculateResponse | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState<string | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [guardrail, setGuardrail] = useState<GuardrailDisplay | null>(null)
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [evidence, setEvidence] = useState<Record<string, string>>({})

  useEffect(() => {
    let alive = true
    fetchLaundryItems().then((data) => {
      if (!alive) return
      if (data) setItems(data)
      else setItemsError(true)
    })
    return () => {
      alive = false
    }
  }, [])

  const valueText = (name: string, value: string): string => {
    if (value === 'yes') return '예'
    if (value === 'no') return '아니오'
    if (value === UNLISTED) return LAUNDRY_TEXT.unlistedOption
    if (name === 'item_key') return items.find((i) => i.key === value)?.label ?? value
    if (LAUNDRY_VALUE_LABEL[name]?.[value]) return LAUNDRY_VALUE_LABEL[name][value]
    if (['purchase_price', 'laundry_fee', 'provider_offer'].includes(name)) return `${Number(value).toLocaleString('ko-KR')}원`
    return value
  }

  const onAnalyze = async (text: string) => {
    setAnalyzeError(null)
    setError(null)
    setAnalyzing(true)
    let outcome: Awaited<ReturnType<typeof analyze>>
    try {
      outcome = await analyze(text, 'laundry')
    } finally {
      setAnalyzing(false)
    }
    if (outcome.kind === 'error') {
      if (outcome.code && ANALYZE_UNAVAILABLE_CODES.has(outcome.code)) {
        onAnalyzeUnavailable(outcome.message) // 패널 대신 안내를 보여 주고 폼으로 이어진다
        return
      }
      setAnalyzeError(outcome.message)
      return
    }
    const data = outcome.data
    setResponse(null)
    setFieldErrors({})
    if (data.status === 'guardrail' && data.guardrail) {
      setGuardrail(data.guardrail)
      setAnalysis(null)
      setNotes({})
      setEvidence({})
      return
    }
    const ext = data.extraction as LaundryAnalyzeResult | null
    if (!ext) {
      setAnalyzeError(ANALYZE_TEXT.filled(0))
      return
    }
    setGuardrail(null)
    const merged = mergeLaundryExtraction(form, touched, ext, items)
    setForm(merged.form)
    const formKey = laundryFormKey
    // 되묻기 규칙은 laundryFollowUpFields
    const { missing, unverified } = laundryFollowUpFields(ext, merged.form, touched)
    const conflicts = Object.keys(merged.conflicts)
    const filled = new Set<string>(merged.filled)
    const confirm = ext.confirm.filter((f) => filled.has(formKey(f)))
    const nextNotes: Record<string, string> = {}
    for (const f of unverified) nextNotes[formKey(f)] = ANALYZE_TEXT.unverifiedNote
    for (const f of missing) nextNotes[formKey(f)] = ANALYZE_TEXT.missingNote
    for (const f of confirm) {
      nextNotes[formKey(f)] = SELECTION.has(f)
        ? LAUNDRY_TEXT.selectionNote
        : f === 'proof_available'
          ? LAUNDRY_TEXT.routeNote
          : ANALYZE_TEXT.confirmNote
    }
    for (const [f, v] of Object.entries(merged.conflicts)) {
      nextNotes[f] = ANALYZE_TEXT.conflictNote(valueText(f, v as string))
    }
    setNotes(nextNotes)
    setEvidence(
      Object.fromEntries(
        Object.entries(ext.evidence)
          .filter((e): e is [string, string] => !!e[1] && filled.has(formKey(e[0])))
          .map(([k, t]) => [formKey(k), t]),
      ),
    )
    setAnalysis({
      filledCount: merged.filled.length,
      missing,
      unverified,
      conflicts,
      confirm,
      piiMasked: data.pii_masked,
    })
  }

  const onSubmit = async () => {
    setError(null)
    setFieldErrors({})
    const built = buildLaundryInput(form, items)
    if (!built.ok) {
      const errs: Record<string, string> = {}
      for (const f of built.invalidFields) errs[f] = INPUT_ERROR.won
      for (const f of built.missingFields) errs[f] = INPUT_ERROR.required
      setFieldErrors(errs)
      setResponse(null)
      return
    }
    setSubmitting(true)
    let outcome: Awaited<ReturnType<typeof calculateLaundry>>
    try {
      outcome = await calculateLaundry(built.input)
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
      setError(
        `${outcome.message} (${Object.keys(errs)
          .map((f) => (f === 'body' ? INPUT_ERROR.body : (LAUNDRY_FIELD_LABEL[f] ?? f)))
          .join(', ')})`,
      )
      return
    }
    setError(outcome.message)
  }

  return (
    <main className="app">
      <header>
        <h1>기준대로</h1>
        <p className="lead">{LAUNDRY_TEXT.lead}</p>
        <p className="supported">{LAUNDRY_TEXT.supported}</p>
      </header>
      {analyzeOff === null ? (
        <AnalyzePanel
          onAnalyze={onAnalyze}
          analyzing={analyzing}
          placeholder={LAUNDRY_TEXT.placeholder}
          idPrefix="laundry-"
          examples={EXAMPLES.laundry}
        />
      ) : (
        <p className="analyze-off" role="status" data-testid="analyze-off">
          {analyzeOff}
        </p>
      )}
      {analyzeError && (
        <p className="request-error analyze-error" role="alert">
          {analyzeError}
        </p>
      )}
      {itemsError && (
        <p className="request-error" role="alert">
          {LAUNDRY_TEXT.itemsLoadError}
        </p>
      )}
      <div className="layout">
        <div>
          {analysis && <FollowUp {...analysis} labels={LAUNDRY_FIELD_LABEL} />}
          <LaundryForm
            form={form}
            items={items}
            onChange={(next) => {
              const changed = (Object.keys(next) as (keyof Form)[]).filter((k) => next[k] !== form[k])
              if (changed.length > 0) setTouched(new Set([...touched, ...changed]))
              setNotes(without(notes, form, next))
              setEvidence(without(evidence, form, next))
              setForm(next)
              setResponse(null) // 입력을 바꾸면 이전 결과를 지운다
              setGuardrail(null)
            }}
            onSubmit={onSubmit}
            submitting={submitting}
            fieldErrors={fieldErrors}
            notes={notes}
            evidence={evidence}
          />
        </div>
        <div className="output">
          {guardrail && <GuardrailCard data={guardrail} />}
          {error && (
            <p className="request-error" role="alert">
              {error}
            </p>
          )}
          {response && <LaundryResultCard data={response} />}
          {response && calcInput && <GuidePanel item="laundry" input={calcInput} surveyUrl={surveyUrl} />}
        </div>
      </div>
    </main>
  )
}
