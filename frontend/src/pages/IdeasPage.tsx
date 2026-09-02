import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { apiGet, apiPatch, apiPost, apiDelete, friendlyMessage } from '../api/client'
import type { ArchiveSearchResult, IdeaCard, OnboardingStatus, PlanItemOut } from '../api/types'
import { DeskPage } from '../components/DeskPage'
import { FeedbackButtons } from '../components/FeedbackButtons'
import { CharCounter, EmptyState, WhyBlockView } from '../components/Shared'
import { useDesk } from '../hooks/useDesk'
import { useDeskStore } from '../store/ui'
import { useUiStore } from '../store/ui'

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const STATUS_LABEL: Record<string, string> = {
  conceived: 'задумано',
  written: 'написано',
  published: 'опубликовано',
}
const STATUS_ORDER = ['conceived', 'written', 'published'] as const

function weekBounds(today = new Date()) {
  const d = new Date(today)
  const day = d.getDay()
  const diff = day === 0 ? -6 : 1 - day
  const monday = new Date(d)
  monday.setDate(d.getDate() + diff)
  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)
  return { monday, sunday }
}

function PlanItemEditor({ item, onSaved }: { item: PlanItemOut; onSaved: () => void }) {
  const navigate = useNavigate()
  const { showToast } = useUiStore()
  const { setDraftFromNav, setPlanItemId } = useDeskStore()
  const [status, setStatus] = useState(item.status)
  const [draft, setDraft] = useState(item.draft_text)
  const [dateVal, setDateVal] = useState(item.scheduled_date?.slice(0, 10) ?? '')

  const save = async () => {
    try {
      await apiPatch(`/plan/${item.id}`, {
        status,
        draft_text: draft,
        scheduled_date: dateVal || null,
      })
      showToast('Сохранено')
      onSaved()
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  const remove = async () => {
    try {
      await apiDelete(`/plan/${item.id}`)
      showToast('Удалено из плана')
      onSaved()
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  return (
    <details className="desk-card desk-card--fold">
      <summary className="desk-card-title">
        {item.title} · {STATUS_LABEL[status]}
      </summary>
      <select className="desk-input" value={status} onChange={(e) => setStatus(e.target.value as PlanItemOut['status'])}>
        {STATUS_ORDER.map((s) => (
          <option key={s} value={s}>
            {STATUS_LABEL[s]}
          </option>
        ))}
      </select>
      <textarea className="desk-textarea" value={draft} onChange={(e) => setDraft(e.target.value)} rows={5} />
      <CharCounter text={draft} />
      <input className="desk-input" type="date" value={dateVal} onChange={(e) => setDateVal(e.target.value)} />
      <div className="desk-actions">
        <button type="button" className="btn btn-primary" onClick={save}>
          сохранить
        </button>
        <button
          type="button"
          className="text-btn"
          onClick={() => {
            setDraftFromNav(draft || item.title)
            setPlanItemId(item.id)
            navigate('/desk/text')
          }}
        >
          редактировать текст
        </button>
        <button type="button" className="text-btn" onClick={remove}>
          удалить
        </button>
      </div>
    </details>
  )
}

export function IdeasPage() {
  const navigate = useNavigate()
  const { showToast } = useUiStore()
  const { rememberPlan } = useDesk()
  const setDraftFromNav = useDeskStore((s) => s.setDraftFromNav)
  const [count, setCount] = useState(3)
  const [ideas, setIdeas] = useState<IdeaCard[]>([])
  const [seasonal, setSeasonal] = useState<ArchiveSearchResult | null>(null)
  const [generating, setGenerating] = useState(false)

  const statusQuery = useQuery({
    queryKey: ['onboarding', 'status'],
    queryFn: () => apiGet<OnboardingStatus>('/onboarding/status'),
  })

  const planQuery = useQuery({
    queryKey: ['plan'],
    queryFn: () => apiGet<PlanItemOut[]>('/plan'),
  })

  const postsN = statusQuery.data?.posts_imported ?? 0

  const ideasQuery = useQuery({
    queryKey: ['ideas'],
    queryFn: () => apiGet<{ ideas: IdeaCard[] }>('/ideas'),
    enabled: postsN > 0,
  })

  useEffect(() => {
    if (ideas.length === 0 && (ideasQuery.data?.ideas?.length ?? 0) > 0) {
      setIdeas(ideasQuery.data!.ideas)
    }
  }, [ideasQuery.data, ideas.length])

  const rhythmQuery = useQuery({
    queryKey: ['rhythm'],
    queryFn: () => apiGet<{ hint: string }>('/rhythm/hint'),
  })

  const generate = async () => {
    setGenerating(true)
    try {
      const batch = await apiPost<{ ideas: IdeaCard[] }>('/ideas/generate', { count })
      setIdeas(batch.ideas ?? [])
    } catch (exc) {
      showToast(friendlyMessage(exc))
    } finally {
      setGenerating(false)
    }
  }

  const loadSeasonal = async () => {
    try {
      const data = await apiGet<ArchiveSearchResult>('/archive/seasonal')
      setSeasonal(data)
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  const weekPlan = useMemo(() => {
    const plan = planQuery.data ?? []
    const { monday, sunday } = weekBounds()
    const byDay = new Map<string, PlanItemOut[]>()
    const undated: PlanItemOut[] = []
    const outside: PlanItemOut[] = []
    for (const item of plan) {
      const raw = item.scheduled_date?.slice(0, 10)
      if (!raw) {
        undated.push(item)
        continue
      }
      const d = new Date(raw)
      if (d >= monday && d <= sunday) {
        const key = raw
        byDay.set(key, [...(byDay.get(key) ?? []), item])
      } else {
        outside.push(item)
      }
    }
    return { monday, byDay, undated, outside }
  }, [planQuery.data])

  const toPlan = async (ideaId: number) => {
    try {
      const item = await apiPost<PlanItemOut>(`/ideas/${ideaId}/to-plan`)
      await rememberPlan(item.id)
      showToast('В плане')
      planQuery.refetch()
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  return (
    <DeskPage title="Идеи и план" subtitle="Идеи из архива. План — если сама захочешь.">
      <section className="desk-section">
        <h2 className="desk-section-title">Из архива к сезону</h2>
        <button type="button" className="btn btn-secondary" onClick={loadSeasonal}>
          показать сезонные
        </button>
        {seasonal && (
          <>
            <WhyBlockView why={seasonal.why} />
            {(seasonal.hits ?? []).map((hit, i) => (
              <div key={i} className="desk-card">
                <p className="desk-card-title">
                  {hit.theme} · отклик {hit.engagement?.toFixed(0)}
                </p>
                <p className="desk-prose">{hit.text_preview}</p>
                <p className="muted">{hit.why_relevant}</p>
              </div>
            ))}
          </>
        )}
      </section>

      <section className="desk-section">
        <h2 className="desk-section-title">Новые идеи</h2>
      {postsN === 0 ? (
        <EmptyState>Сначала нужны твои тексты — иначе идеи будут с потолка.</EmptyState>
      ) : (
        <>
          <label className="desk-range">
            Сколько идей
            <input
              type="range"
              min={2}
              max={6}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
            />
            <span>{count}</span>
          </label>
          <div className="desk-actions">
            <button type="button" className="btn btn-primary" disabled={generating} onClick={generate}>
              {generating ? 'идеи…' : 'предложить идеи'}
            </button>
          </div>
          {ideas.map((idea, i) => (
            <div key={idea.id ?? i} className="desk-card">
              <h3 className="desk-card-title">{idea.theme}</h3>
              <p className="desk-prose">{idea.description}</p>
              <p className="muted">
                {idea.format} · усилие: {idea.effort} · {idea.personal_angle}
              </p>
              {idea.why_now && <p className="desk-prose">Почему сейчас: {idea.why_now}</p>}
              <WhyBlockView why={idea.why} />
              {idea.suggestion_id && <FeedbackButtons suggestionId={idea.suggestion_id} />}
              <div className="desk-actions">
                {idea.id && (
                  <button type="button" className="text-btn" onClick={() => toPlan(idea.id!)}>
                    в план
                  </button>
                )}
                <button
                  type="button"
                  className="text-btn"
                  onClick={() => {
                    setDraftFromNav(
                      `${idea.theme}\n\n${idea.personal_angle || ''}\n\n${idea.description || ''}`,
                    )
                    navigate('/desk/text')
                  }}
                >
                  к черновику
                </button>
              </div>
            </div>
          ))}
        </>
      )}
      </section>

      <section className="desk-section">
        <h2 className="desk-section-title">План на неделю</h2>
      {rhythmQuery.data?.hint && <p className="muted">{rhythmQuery.data.hint}</p>}
      {!planQuery.data?.length ? (
        <EmptyState>План пуст — добавь идею или импортируй из архива.</EmptyState>
      ) : (
        <>
          <div className="week-grid">
            {WEEKDAYS.map((wd, offset) => {
              const day = new Date(weekPlan.monday)
              day.setDate(weekPlan.monday.getDate() + offset)
              const key = day.toISOString().slice(0, 10)
              const items = weekPlan.byDay.get(key) ?? []
              const isToday = key === new Date().toISOString().slice(0, 10)
              return (
                <div key={wd}>
                  <div className={isToday ? 'tr-day tr-day--today' : 'tr-day'}>
                    {wd} · {day.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}
                  </div>
                  {items.length === 0 ? (
                    <span className="muted">—</span>
                  ) : (
                    items.map((item) => (
                      <div key={item.id} className="tr-chip">
                        <strong>{item.title.slice(0, 40)}</strong>
                        <br />
                        {STATUS_LABEL[item.status]}
                      </div>
                    ))
                  )}
                </div>
              )
            })}
          </div>
          <h3 className="desk-subsection-title">Правки</h3>
          {planQuery.data.map((item) => (
            <PlanItemEditor key={item.id} item={item} onSaved={() => planQuery.refetch()} />
          ))}
        </>
      )}
      </section>
    </DeskPage>
  )
}
