import { useState, type FormEvent } from 'react'

const MAX_ROUNDS = 3

type Requirement = {
  project_id: string
  id: string
  category: string
  description: string
  status: 'confirmed' | 'needs_clarification' | 'proposed'
  source: string
  blocking: boolean
  acceptance_criteria: string[]
}

type Gap = {
  id: string
  category: string
  description: string
  blocking: boolean
  related_requirement_ids: string[]
}

type Analysis = {
  project_id: string
  run_id: string
  clarification_round: number
  requirements: Requirement[]
  gaps: Gap[]
  clarification_needed: boolean
  analysis_mode: 'mock' | 'snowchat'
  usage: Record<string, unknown>[]
}

type ClarificationQuestion = {
  gap_id: string
  question: string
  ai_proposal: string // 질문 단계에서는 표시하지 않는다
}

type Answer = { gap_id: string; answer: string }

type ClarificationRound = {
  round: number
  gaps: Gap[]
  questions: ClarificationQuestion[]
  answers: Answer[]
}

type WorkflowState = Analysis & {
  text: string
  phase: 'clarifying' | 'review' | 'approved'
  questions: ClarificationQuestion[]
  history: ClarificationRound[]
  edit_count: number
}

// detail 형식: {code, message} | 문자열(빈 입력) | 배열(FastAPI 요청 스키마 422)
async function post<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const detail = (await response.json().catch(() => null))?.detail
    const message = typeof detail?.message === 'string' ? detail.message : typeof detail === 'string' ? detail : null
    throw new Error(message ?? `요청 실패 (${response.status})`)
  }
  return await response.json() as T
}

export default function App() {
  const [text, setText] = useState('')
  const [state, setState] = useState<WorkflowState | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [loading, setLoading] = useState('')

  // 질문 대기 중이면 답변 라운드, 아니면 분석 직후 첫 호출(answers 없이)
  async function step(current: WorkflowState) {
    const waiting = current.questions.length > 0
    setLoading(waiting ? '답변 반영 및 재분석 중… (약 30초)' : '확인 질문 생성 중… (약 30초)')
    setError('')
    try {
      const body = waiting
        ? { state: current, answers: current.questions.map(q => ({ gap_id: q.gap_id, answer: answers[q.gap_id] ?? '' })) }
        : { state: current }
      setState(await post<WorkflowState>('/api/clarification/step', body))
      setAnswers({})
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Clarification 요청에 실패했습니다.')
    } finally {
      setLoading('')
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!text.trim()) {
      setError('요구사항을 입력해주세요.')
      return
    }
    setLoading('요구사항 분석 중… (최대 1분)')
    setError('')
    let analysis: Analysis
    try {
      analysis = await post<Analysis>('/api/requirements/analyze', { text })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '분석 요청에 실패했습니다.')
      setLoading('')
      return
    }
    const initial: WorkflowState = { ...analysis, text, phase: 'clarifying', questions: [], history: [], edit_count: 0 }
    setState(initial)
    await step(initial)
  }

  function reset() {
    setState(null)
    setAnswers({})
    setError('')
  }

  return (
    <main>
      <h1>자연어 요구사항 분석</h1>
      <p>서비스 요구사항을 입력하면 구조화된 항목과 확인이 필요한 부분을 표시합니다.</p>
      <form onSubmit={submit}>
        <label htmlFor="requirement-text">서비스 요구사항</label>
        <textarea id="requirement-text" value={text} onChange={event => setText(event.target.value)} rows={5} disabled={!!state} />
        {state
          ? <button key="reset" type="button" onClick={reset} disabled={!!loading}>처음부터 다시</button>
          : <button key="analyze" disabled={!!loading}>분석하기</button>}
      </form>
      {loading && <p className="notice" role="status">{loading}</p>}
      {error && <p role="alert" className="error">{error}</p>}
      {state && (
        <section aria-live="polite">
          <p className="notice">{state.analysis_mode === 'snowchat' ? 'SnowChat LLM 분석 결과' : 'Mock 분석 결과 · 규칙 기반 시연'}</p>

          {state.phase === 'clarifying' && state.questions.length > 0 && (
            <form onSubmit={event => { event.preventDefault(); step(state) }}>
              <h2>확인 질문 (라운드 {state.clarification_round}/{MAX_ROUNDS})</h2>
              <p>답하기 어려운 질문은 비워 두면 건너뜁니다. {MAX_ROUNDS}라운드 뒤에도 남은 항목은 AI 제안으로 전환됩니다.</p>
              {state.questions.map(q => (
                <div key={q.gap_id}>
                  <label htmlFor={`answer-${q.gap_id}`}><strong>{q.gap_id}</strong> {q.question}</label>
                  <textarea id={`answer-${q.gap_id}`} rows={2} value={answers[q.gap_id] ?? ''} disabled={!!loading}
                    onChange={event => setAnswers({ ...answers, [q.gap_id]: event.target.value })} />
                </div>
              ))}
              <button disabled={!!loading}>답변 제출</button>
            </form>
          )}
          {state.phase === 'clarifying' && state.questions.length === 0 && !loading && (
            <button type="button" onClick={() => step(state)}>확인 질문 생성 다시 시도</button>
          )}
          {state.phase !== 'clarifying' && (
            <p className="notice">Clarification이 끝났습니다. Requirement Review 단계로 이동합니다. (Review 화면은 다음 작업에서 구현)</p>
          )}

          <h2>현재 요구사항</h2>
          <ul>
            {state.requirements.map(requirement => (
              <li key={requirement.id}>
                <strong>{requirement.id}</strong> [{requirement.category} · {requirement.status} · {requirement.source}]
                {requirement.blocking && ' · 진행 보류'} — {requirement.description}
              </li>
            ))}
          </ul>
          {/* review 이후 gaps는 마지막 분석 결과라 blocking 값을 신뢰하지 않는다 */}
          {state.phase === 'clarifying' && (
            <>
              <h2>확인이 필요한 부분</h2>
              {state.gaps.length === 0 ? <p>발견된 Gap이 없습니다.</p> : (
                <ul>
                  {state.gaps.map(gap => (
                    <li key={gap.id}>
                      <strong>{gap.id}</strong> [{gap.category} · {gap.blocking ? '핵심' : '참고'}]
                      {' '}{gap.description}
                      <small>관련 요구사항: {gap.related_requirement_ids.join(', ') || '서비스 전반'}</small>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>
      )}
    </main>
  )
}
