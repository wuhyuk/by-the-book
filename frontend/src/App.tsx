import { useState } from 'react'
import { calculate } from './api'
import { GymForm } from './components/GymForm'
import { ResultCard } from './components/ResultCard'
import { buildInput, COUNT_FIELDS, INITIAL_FORM, type FormState } from './formState'
import { FIELD_LABEL, INPUT_ERROR, ISSUE_TYPE_LABEL, SUPPORTED_INDUSTRIES } from './texts'
import type { CalculateResponse } from './types'
import './App.css'

// 상태는 이 컴포넌트의 useState로만 둔다. 입력값을 URL·localStorage·콘솔에 남기지 않는다.
function App() {
  const [form, setForm] = useState<FormState>(INITIAL_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [response, setResponse] = useState<CalculateResponse | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

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
      <div className="layout">
        <GymForm
          form={form}
          onChange={(next) => {
            setForm(next)
            setResponse(null) // 입력을 바꾸면 이전 결과를 지운다 (다른 입력의 결과를 보여 주지 않도록)
          }}
          onSubmit={onSubmit}
          submitting={submitting}
          fieldErrors={fieldErrors}
        />
        <div className="output">
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
