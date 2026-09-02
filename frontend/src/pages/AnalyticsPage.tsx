import { Suspense, lazy, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiGet, friendlyMessage } from '../api/client'
import type { AnalyticsOut, AudienceReport } from '../api/types'
import { DeskPage } from '../components/DeskPage'
import { FeedbackButtons } from '../components/FeedbackButtons'
import { EmptyState, WhyBlockView } from '../components/Shared'
import { useUiStore } from '../store/ui'

const AnalyticsChart = lazy(() =>
  import('../components/AnalyticsChart').then((m) => ({ default: m.AnalyticsChart })),
)

export function AnalyticsPage() {
  const { showToast } = useUiStore()
  const [report, setReport] = useState<AudienceReport | null>(null)
  const [loadingReport, setLoadingReport] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['analytics'],
    queryFn: () => apiGet<AnalyticsOut>('/analytics', { with_report: 'false' }),
  })

  const loadReport = async () => {
    setLoadingReport(true)
    try {
      const out = await apiGet<AnalyticsOut>('/analytics', { with_report: true })
      setReport(out.report ?? null)
    } catch (exc) {
      showToast(friendlyMessage(exc))
    } finally {
      setLoadingReport(false)
    }
  }

  if (isLoading) return <p className="muted desk-loading">Загрузка…</p>

  if (!data?.posts_count) {
    return (
      <DeskPage title="Аналитика" subtitle="Что заходило — по архиву">
        <EmptyState>Здесь пока тихо — вставь свои посты, и я буду опираться на них.</EmptyState>
      </DeskPage>
    )
  }

  return (
    <DeskPage title="Аналитика" subtitle="Что заходило — по архиву">
      {(data.series ?? []).length > 0 && (
        <Suspense fallback={<p className="muted">График…</p>}>
          <AnalyticsChart series={data.series as { date: string; engagement: number }[]} />
        </Suspense>
      )}

      {(data.top_posts ?? []).length > 0 && (
        <section className="desk-section">
          <h2 className="desk-section-title">Топ-посты</h2>
          {data.top_posts.map((p, i) => (
            <p key={i} className="desk-list-item">
              <strong>{p.theme || 'без темы'}</strong> · отклик {p.engagement?.toFixed(0)} —{' '}
              {(p.text || '').slice(0, 120)}
            </p>
          ))}
        </section>
      )}

      <section className="desk-section">
        <h2 className="desk-section-title">Выводы</h2>
        <p className="muted">Если захочешь — соберу словами.</p>
        <button type="button" className="btn btn-primary" disabled={loadingReport} onClick={loadReport}>
          сделать выводы
        </button>
      </section>

      {report && (
        <div className="desk-card">
          <p>{report.portrait}</p>
          <WhyBlockView why={report.why} />
          {report.suggestion_id && <FeedbackButtons suggestionId={report.suggestion_id} />}
          {(
            [
              ['what_works', 'Что работает'],
              ['frequent_questions', 'Частые вопросы'],
              ['unmet_needs', 'Незакрытые запросы'],
              ['recommendations', 'Делать чаще'],
            ] as const
          ).map(([key, title]) => {
            const items = report[key] ?? []
            if (!items.length) return null
            return (
              <div key={key} className="desk-subsection">
                <h3 className="desk-subsection-title">{title}</h3>
                {items.map((line, i) => (
                  <p key={i} className="desk-list-item">
                    · {line}
                  </p>
                ))}
              </div>
            )
          })}
        </div>
      )}
    </DeskPage>
  )
}
