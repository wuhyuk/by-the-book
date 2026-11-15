// 관련 조항 (자동 검색, 기능 플래그 rag). 후보·AI가 고른 표시는 /api/analyze의 clauses 그대로이고,
// 펼치면 /api/sources/{id}로 저장된 원문을 불러온다. 금액 계산에는 쓰지 않는다.
import { useState } from 'react'
import { fetchSource } from '../api'
import { clauseStatus } from '../clauses'
import { CLAUSE_TEXT } from '../texts'
import type { ClauseSource, ClauseSuggestions } from '../types'

type SourceState = { kind: 'loading' } | { kind: 'ok'; data: ClauseSource } | { kind: 'error' }

export function ClausePanel({ data }: { data: ClauseSuggestions }) {
  const [sources, setSources] = useState<Record<string, SourceState>>({})
  const picked = new Set(data.selected.map((s) => s.clause_id))

  const load = (id: string) => {
    if (sources[id]) return
    setSources((prev) => ({ ...prev, [id]: { kind: 'loading' } }))
    fetchSource(id).then((res) =>
      setSources((prev) => ({ ...prev, [id]: res ? { kind: 'ok', data: res } : { kind: 'error' } })),
    )
  }

  return (
    <section className="clause-panel" aria-label={CLAUSE_TEXT.title} data-testid="clause-panel">
      <h3>{CLAUSE_TEXT.title}</h3>
      <p className="hint">{CLAUSE_TEXT.note}</p>
      {data.candidates.length === 0 && <p className="hint">{CLAUSE_TEXT.none}</p>}
      <ul className="clause-list">
        {data.candidates.map((c) => {
          const [machine, user] = clauseStatus(c.verified, c.user_checked)
          const st = sources[c.clause_id]
          return (
            <li key={c.clause_id} data-testid={`clause-${c.clause_id}`}>
              <details onToggle={(e) => e.currentTarget.open && load(c.clause_id)}>
                <summary>
                  {picked.has(c.clause_id) && (
                    <span className="basis-tag basis-official" data-testid="clause-picked">
                      {CLAUSE_TEXT.aiPicked}
                    </span>
                  )}{' '}
                  <strong>{c.title}</strong> · {c.source_name}{' '}
                  <span className="hint">({CLAUSE_TEXT.showSource})</span>
                </summary>
                <p className="hint">{c.excerpt}</p>
                <p className="hint">
                  {CLAUSE_TEXT.retrievedAt(c.retrieved_at)} · {machine} · {user}
                </p>
                {st?.kind === 'loading' && <p className="hint">{CLAUSE_TEXT.loading}</p>}
                {st?.kind === 'error' && <p className="hint">{CLAUSE_TEXT.failed}</p>}
                {st?.kind === 'ok' && (
                  <>
                    <blockquote data-testid="clause-source-text">{st.data.text}</blockquote>
                    <p className="source">
                      {CLAUSE_TEXT.source}:{' '}
                      <a href={st.data.source.url} target="_blank" rel="noreferrer noopener">
                        {st.data.source.name}
                      </a>{' '}
                      ({CLAUSE_TEXT.retrievedAt(st.data.retrieved_at)})
                    </p>
                  </>
                )}
              </details>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
