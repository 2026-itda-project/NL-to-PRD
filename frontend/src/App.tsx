import { useState, type FormEvent } from 'react'

type Requirement = {
  id: string
  category: string
  description: string
  status: 'confirmed' | 'needs_clarification' | 'proposed'
  source: string
  blocking: boolean
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
  requirements: Requirement[]
  gaps: Gap[]
  clarification_needed: boolean
  analysis_mode: 'mock' | 'snowchat'
}

export default function App() {
  const [text, setText] = useState('')
  const [result, setResult] = useState<Analysis | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!text.trim()) {
      setError('요구사항을 입력해주세요.')
      setResult(null)
      return
    }
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const response = await fetch('/api/requirements/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.detail?.message ?? `분석 요청 실패 (${response.status})`)
      }
      setResult(await response.json() as Analysis)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '분석 요청에 실패했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main>
      <h1>자연어 요구사항 분석</h1>
      <p>서비스 요구사항을 입력하면 구조화된 항목과 확인이 필요한 부분을 표시합니다.</p>
      <form onSubmit={submit}>
        <label htmlFor="requirement-text">서비스 요구사항</label>
        <textarea id="requirement-text" value={text} onChange={event => setText(event.target.value)} rows={5} />
        <button disabled={loading}>{loading ? '분석 중…' : '분석하기'}</button>
      </form>
      {error && <p role="alert" className="error">{error}</p>}
      {result && (
        <section aria-live="polite">
          <p className="notice">{result.analysis_mode === 'snowchat' ? 'SnowChat LLM 분석 결과' : 'Mock 분석 결과 · 규칙 기반 시연'}</p>
          <p>{result.clarification_needed ? '핵심 확인 사항이 있습니다.' : '현재 발견된 핵심 확인 사항이 없습니다.'}</p>
          <h2>추출된 요구사항</h2>
          <ul>
            {result.requirements.map(requirement => (
              <li key={requirement.id}>
                <strong>{requirement.id}</strong> [{requirement.category} · {requirement.status}]
                {requirement.blocking && ' · 진행 보류'} — {requirement.description}
              </li>
            ))}
          </ul>
          <h2>확인이 필요한 부분</h2>
          {result.gaps.length === 0 ? <p>발견된 Gap이 없습니다.</p> : (
            <ul>
              {result.gaps.map(gap => (
                <li key={gap.id}>
                  <strong>{gap.id}</strong> [{gap.category} · {gap.blocking ? '핵심' : '참고'}]
                  {' '}{gap.description}
                  <small>관련 요구사항: {gap.related_requirement_ids.join(', ') || '서비스 전반'}</small>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </main>
  )
}
