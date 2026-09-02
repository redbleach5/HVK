import { useQuery } from '@tanstack/react-query'
import { apiGet, apiPost, friendlyMessage } from '../api/client'
import type { TodayResponse } from '../api/types'
import { DeskPage } from '../components/DeskPage'
import { FeedbackButtons } from '../components/FeedbackButtons'
import { EmptyState, WhyBlockView } from '../components/Shared'
import { useUiStore } from '../store/ui'

export function TodayPage() {
  const { showToast } = useUiStore()
  const { data, isLoading, error } = useQuery({
    queryKey: ['today'],
    queryFn: () => apiGet<TodayResponse>('/today'),
  })

  if (isLoading) return <p className="muted desk-loading">Загрузка…</p>
  if (error) return <p className="muted desk-loading">Не получилось загрузить сводку.</p>

  const toPlan = async (ideaId: number) => {
    try {
      await apiPost(`/ideas/${ideaId}/to-plan`)
      showToast('В плане')
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  return (
    <DeskPage title="Сегодня" subtitle="Сводка, идеи и план">
      <div className="desk-card desk-card--lead">
        <p className="desk-prose">{data?.digest}</p>
        {(data?.highlights ?? []).map((h, i) => (
          <p key={i} className="desk-list-item">
            · {h.text}
          </p>
        ))}
        <WhyBlockView why={data?.why} />
      </div>

      {(data?.ideas ?? []).length > 0 ? (
        <section className="desk-section">
          <h2 className="desk-section-title">Идеи</h2>
          {data!.ideas.map((idea, i) => (
            <div key={idea.id ?? i} className="desk-card">
              <p className="desk-card-title">
                {idea.theme} · {idea.format || 'формат свободный'}
              </p>
              <p className="desk-prose">{idea.description}</p>
              {idea.why_now && <p className="muted">{idea.why_now}</p>}
              <WhyBlockView why={idea.why} />
              {idea.suggestion_id && <FeedbackButtons suggestionId={idea.suggestion_id} />}
              {idea.id && (
                <button type="button" className="text-btn" onClick={() => toPlan(idea.id!)}>
                  в план
                </button>
              )}
            </div>
          ))}
        </section>
      ) : (
        <EmptyState>
          Карточек в этой сводке ещё нет. Когда захочешь — спроси в чате про идеи.
        </EmptyState>
      )}

      {(data?.plan_reminders ?? []).length > 0 && (
        <section className="desk-section">
          <h2 className="desk-section-title">План</h2>
          {data!.plan_reminders.map((line, i) => (
            <p key={i} className="desk-list-item">
              · {line}
            </p>
          ))}
        </section>
      )}
    </DeskPage>
  )
}
