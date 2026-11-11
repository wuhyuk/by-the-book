import { useState } from 'react'
import { analyze, calculate } from './api'
import { AnalyzePanel } from './components/AnalyzePanel'
import { FollowUp } from './components/FollowUp'
import { GuardrailCard } from './components/GuardrailCard'
import { GymForm } from './components/GymForm'
import { ResultCard } from './components/ResultCard'
import {
  buildInput,
  COUNT_FIELDS,
  INITIAL_FORM,
  followUpFields,
  mergeExtraction,
  type FormState,
} from './formState'
import { ANALYZE_TEXT, FIELD_LABEL, INPUT_ERROR, ISSUE_TYPE_LABEL, SUPPORTED_INDUSTRIES, VALUE_LABEL } from './texts'
import type { CalculateResponse, GuardrailDisplay } from './types'

interface Analysis {
  filledCount: number
  missing: string[]
  unverified: string[]
  conflicts: string[]
  confirm: string[]
  piiMasked: boolean
}

const AMOUNT_FIELDS = new Set(['total_contract_amount', 'paid_amount', 'add_on_value', 'returned_add_on_value', 'deposit', 'list_price', 'contract_penalty', 'provider_offer'])

/** 문장 값(폼 값 형식)을 사람이 읽는 문구로. 숫자는 서버가 확인한 정수를 형식만 바꾼다. */
function valueText(name: string, value: FormState[keyof FormState]): string {
  if (typeof value === 'boolean') return value ? '예' : '아니오'
  if (value === 'yes') return '예'
  if (value === 'no') return '아니오'
  if (VALUE_LABEL[name]?.[value]) return VALUE_LABEL[name][value]
  if (AMOUNT_FIELDS.has(name)) return `${Number(value).toLocaleString('ko-KR')}원`
  if (COUNT_FIELDS.includes(name)) return `${value}회`
  return value
}

function without(rec: Record<string, string>, form: FormState, next: FormState): Record<string, string> {
  const keys = Object.keys(rec).filter((k) => k in next && next[k as keyof FormState] === form[k as keyof FormState])
  return Object.fromEntries(keys.map((k) => [k, rec[k]]))
}
import './App.css'

// 상태는 이 컴포넌트의 useState로만 둔다. 입력값을 URL·localStorage·콘솔에 남기지 않는다.
function App() {
  const [form, setForm] = useState<FormState>(INITIAL_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [response, setResponse] = useState<CalculateResponse | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  // 문장 분석 (VS3). 문장 자체는 AnalyzePanel 상태에만 있고 여기에는 결과만 둔다.
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState<string | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [guardrail, setGuardrail] = useState<GuardrailDisplay | null>(null)
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [evidence, setEvidence] = useState<Record<string, string>>({})
  // 사용자가 폼에서 직접 바꾼 항목. 문장 분석은 이 항목의 값을 덮어쓰지 않는다 (결정 B)
  const [touched, setTouched] = useState<ReadonlySet<string>>(new Set())

  const onAnalyze = async (text: string) => {
    setAnalyzeError(null)
    setError(null)
    setAnalyzing(true)
    let outcome: Awaited<ReturnType<typeof analyze>>
    try {
      outcome = await analyze(text)
    } finally {
      setAnalyzing(false)
    }
    if (outcome.kind === 'error') {
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
    const ext = data.extraction
    if (!ext) {
      setAnalyzeError(ANALYZE_TEXT.filled(0))
      return
    }
    setGuardrail(null)
    const merged = mergeExtraction(form, touched, ext)
    setForm(merged.form)
    // 되묻기 안내는 합친 뒤에도 비어 있는 항목에만 붙인다 (규칙은 followUpFields)
    const { missing, unverified } = followUpFields(ext, merged.form, touched)
    const conflicts = Object.keys(merged.conflicts)
    const nextNotes: Record<string, string> = {}
    for (const f of unverified) nextNotes[f] = ANALYZE_TEXT.unverifiedNote
    for (const f of missing) nextNotes[f] = ANALYZE_TEXT.missingNote
    // 계산을 멈추게 하는 값(❔)은 문장 값으로 채운 경우에만 확인 안내를 붙인다
    const confirm = ext.confirm.filter((f) => merged.filled.includes(f as keyof FormState))
    for (const f of confirm) nextNotes[f] = ANALYZE_TEXT.confirmNote
    for (const [f, v] of Object.entries(merged.conflicts)) {
      nextNotes[f] = ANALYZE_TEXT.conflictNote(valueText(f, v as FormState[keyof FormState]))
    }
    setNotes(nextNotes)
    const filled = new Set<string>(merged.filled)
    setEvidence(
      Object.fromEntries(
        Object.entries(ext.evidence).filter((e): e is [string, string] => !!e[1] && filled.has(e[0])),
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
    const built = buildInput(form)
    if (!built.ok) {
      const errs: Record<string, string> = {}
      for (const f of built.invalidFields) errs[f] = COUNT_FIELDS.includes(f) ? INPUT_ERROR.count : INPUT_ERROR.won
      for (const f of built.missingFields) errs[f] = INPUT_ERROR.required
      setFieldErrors(errs)
      setResponse(null)
      return
    }
    setSubmitting(true)
    let outcome: Awaited<ReturnType<typeof calculate>>
    try {
      outcome = await calculate(built.input)
    } finally {
      setSubmitting(false)
    }
    if (outcome.kind === 'ok') {
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
          .map((f) => (f === 'body' ? INPUT_ERROR.body : (FIELD_LABEL[f] ?? f)))
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
        <p className="lead">헬스장·요가·필라테스 중도 해지 환급 기준 금액을 고시의 계산식대로 보여 드립니다.</p>
        <p className="supported">{SUPPORTED_INDUSTRIES}</p>
      </header>
      <AnalyzePanel onAnalyze={onAnalyze} analyzing={analyzing} />
      {analyzeError && (
        <p className="request-error analyze-error" role="alert">
          {analyzeError}
        </p>
      )}
      <div className="layout">
        <div>
          {analysis && <FollowUp {...analysis} />}
          <GymForm
            form={form}
            onChange={(next) => {
              // 사용자가 고친 항목은 되묻기 안내와 문장 근거를 지운다
              const changed = (Object.keys(next) as (keyof FormState)[]).filter((k) => next[k] !== form[k])
              if (changed.length > 0) setTouched(new Set([...touched, ...changed]))
              setNotes(without(notes, form, next))
              setEvidence(without(evidence, form, next))
              setForm(next)
              setResponse(null) // 입력을 바꾸면 이전 결과를 지운다 (다른 입력의 결과를 보여 주지 않도록)
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
          {response && <ResultCard data={response} />}
        </div>
      </div>
    </main>
  )
}

export default App
