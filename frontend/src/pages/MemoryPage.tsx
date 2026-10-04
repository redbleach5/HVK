import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiDelete, apiGet, friendlyMessage } from '../api/client'
import type { MemoryOut } from '../api/types'
import { DeskPage } from '../components/DeskPage'
import { EmptyState } from '../components/Shared'
import { useUiStore } from '../store/ui'

function shortDate(iso?: string | null): string {
  if (!iso) return ''
  return iso.slice(0, 10)
}

/**
 * «Что я запомнила» — то, чему редакция научилась у автора.
 *
 * Раньше обратная связь работала только в одну сторону: автор отвечал
 * «учту» или «не соглашусь», а выученное уходило в подсказки навсегда.
 * Здесь это видно и это можно поправить.
 *
 * Запрет — самое важное: если я поняла настроение неверно и молчу о
 * какой-то теме, автор должен иметь возможность это снять.
 */
export function MemoryPage() {
  const { showToast } = useUiStore()
  const queryClient = useQueryClient()
  const [dropped, setDropped] = useState<number[]>([])

  const { data, isLoading } = useQuery({
    queryKey: ['memory'],
    queryFn: () => apiGet<MemoryOut>('/memory'),
  })

  const forget = useMutation({
    mutationFn: (id: number) => apiDelete<{ ok: boolean; id: number }>(`/memory/antipathies/${id}`),
    onSuccess: (_out, id) => {
      setDropped((prev) => [...prev, id])
      showToast('Забыла 🤍')
      void queryClient.invalidateQueries({ queryKey: ['memory'] })
    },
    onError: (exc) => showToast(friendlyMessage(exc)),
  })

  if (isLoading) return <p className="muted desk-loading">Загрузка…</p>

  const preferences = data?.preferences ?? []
  const antipathies = data?.antipathies ?? []
  const lessons = data?.lessons ?? []

  if (!data?.total) {
    return (
      <DeskPage title="Память" subtitle="Что я о тебе думаю">
        <EmptyState>
          Пока я ничего о тебе не вывела. Отвечай под карточками — «учту» или «не
          соглашусь», — и я стану помнить.
        </EmptyState>
      </DeskPage>
    )
  }

  return (
    <DeskPage title="Память" subtitle="Что я о тебе думаю">
      <p className="muted">
        Здесь всё, чему я научилась. Если я поняла тебя неверно — скажи, и я
        забуду.
      </p>

      <section className="desk-section">
        <h2 className="desk-section-title">Не предлагать</h2>
        {antipathies.length === 0 ? (
          <p className="muted">Пока ничего не запретила.</p>
        ) : (
          <div className="desk-card">
            {antipathies.map((a) => (
              <div key={a.id} className="desk-list-item">
                <strong>{a.topic}</strong>
                {a.why ? <span className="muted"> — {a.why}</span> : null}
                <br />
                <span className="muted">
                  {a.expired
                    ? 'срок вышел — можно забыть'
                    : a.expires_at
                      ? `до ${shortDate(a.expires_at)}`
                      : 'без срока'}
                </span>{' '}
                {forget.isPending ? null : (
                  <button
                    type="button"
                    className="text-btn"
                    onClick={() => forget.mutate(a.id)}
                  >
                    забыть
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="desk-section">
        <h2 className="desk-section-title">Тебе зашло</h2>
        {preferences.length === 0 ? (
          <p className="muted">Пока ничего не отметила.</p>
        ) : (
          <div className="desk-card">
            {preferences.map((p) => (
              <div key={p.id} className="desk-list-item">
                <strong>{p.key}</strong>
                {p.why ? <span className="muted"> — {p.why}</span> : null}
                {p.weight != null && p.weight > 1.05 ? (
                  <span className="muted"> · крепко</span>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="desk-section">
        <h2 className="desk-section-title">Уроки</h2>
        {lessons.length === 0 ? (
          <p className="muted">Уроков пока нет.</p>
        ) : (
          <div className="desk-card">
            {lessons.map((l) => (
              <div key={l.id} className="desk-list-item">
                <strong>{l.title}</strong>
                {l.why ? <span className="muted"> — {l.why}</span> : null}
              </div>
            ))}
          </div>
        )}
      </section>

      {dropped.length > 0 ? (
        <p className="muted">Забыто за этот раз: {dropped.length}</p>
      ) : null}
    </DeskPage>
  )
}
