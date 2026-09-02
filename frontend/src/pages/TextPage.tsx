import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiGet, apiPost, apiPostForm, friendlyMessage } from '../api/client'
import type { EditorResult, HealthStatus, PublishOut } from '../api/types'
import { DeskPage } from '../components/DeskPage'
import { CopyButton } from '../components/CopyButton'
import { FeedbackButtons } from '../components/FeedbackButtons'
import { CharCounter, WhyBlockView } from '../components/Shared'
import { useDesk } from '../hooks/useDesk'
import { useDeskStore } from '../store/ui'
import { useUiStore } from '../store/ui'

function PublishBlock({
  message,
  planItemId,
}: {
  message: string
  planItemId: number | null
}) {
  const { showToast } = useUiStore()
  const health = useQuery({ queryKey: ['health'], queryFn: () => apiGet<HealthStatus>('/health') })
  const [photos, setPhotos] = useState<File[]>([])
  const [confirm, setConfirm] = useState(false)
  const [schedDate, setSchedDate] = useState(() => new Date().toISOString().slice(0, 10))

  if (!health.data?.vk_configured) {
    return (
      <div className="desk-card">
        <h3 className="desk-subsection-title">Опубликовать</h3>
        <p className="muted">VK не подключён — копируй текст и выложи сама.</p>
        <CopyButton text={message} label="скопировать текст" />
      </div>
    )
  }

  const publish = async () => {
    if (!message.trim()) {
      showToast('Нужен текст поста')
      return
    }
    if (!confirm) {
      showToast('Нужна галочка подтверждения')
      return
    }
    const when = new Date(`${schedDate}T12:00:00`)
    const data: Record<string, string> = {
      confirm: 'true',
      message,
      publish_date_unix: String(Math.floor(when.getTime() / 1000)),
    }
    if (planItemId != null) data.plan_item_id = String(planItemId)
    try {
      const out = await apiPostForm<PublishOut>('/publish/form', data, photos)
      showToast('Опубликовано')
      if (out.photos_warning) showToast(out.photos_warning)
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  return (
    <div className="desk-card">
      <h3 className="desk-subsection-title">В VK</h3>
      <p className="muted">Публикация только после подтверждения</p>
      <input type="file" accept="image/*" multiple onChange={(e) => setPhotos(Array.from(e.target.files ?? []))} />
      <label style={{ display: 'block', margin: '0.5rem 0' }}>
        Отложить
        <input type="date" value={schedDate} onChange={(e) => setSchedDate(e.target.value)} />
      </label>
      <label>
        <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} /> подтверждаю
        публикацию
      </label>
      <button type="button" className="btn btn-primary" style={{ marginTop: '0.5rem' }} onClick={publish}>
        опубликовать в VK
      </button>
    </div>
  )
}

export function TextPage() {
  const { showToast } = useUiStore()
  const { draftText, planItemId, setDraftText, saveDesk } = useDesk()
  const draftFromNav = useDeskStore((s) => s.draftFromNav)
  const setDraftFromNav = useDeskStore((s) => s.setDraftFromNav)
  const [topic, setTopic] = useState('')
  const [result, setResult] = useState<EditorResult | null>(null)
  const [revised, setRevised] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (draftFromNav) {
      setDraftText(draftFromNav)
      setDraftFromNav(null)
      saveDesk()
    }
  }, [draftFromNav, setDraftFromNav, setDraftText, saveDesk])

  const edit = async () => {
    if (!draftText.trim()) return
    setLoading(true)
    try {
      const out = await apiPost<EditorResult>('/text/edit', {
        draft: draftText,
        topic_hint: topic,
        plan_item_id: planItemId,
      })
      setResult(out)
      setRevised(out.revised_text || draftText)
      setDraftText(out.revised_text || draftText)
      await saveDesk()
    } catch (exc) {
      showToast(friendlyMessage(exc))
    } finally {
      setLoading(false)
    }
  }

  const applyEdit = async (sid: number, accepted: boolean) => {
    try {
      const out = await apiPost<{ current_text: string }>('/text/apply-edit', {
        suggestion_id: sid,
        accepted,
        current_text: revised,
      })
      setRevised(out.current_text)
      setDraftText(out.current_text)
      showToast(accepted ? 'В тексте' : 'Вернула')
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  return (
    <DeskPage title="Текст" subtitle="Редактура черновика с сохранением голоса">
      <textarea
        className="desk-textarea"
        value={draftText}
        onChange={(e) => setDraftText(e.target.value)}
        onBlur={() => saveDesk()}
        rows={10}
        placeholder="Вставь черновик"
      />
      <CharCounter text={draftText} />
      <input
        className="desk-input"
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
        placeholder="Тема (необязательно)"
      />
      <div className="desk-actions">
        <button type="button" className="btn btn-primary" disabled={loading} onClick={edit}>
          {loading ? 'редактура…' : 'отредактировать'}
        </button>
        <CopyButton text={draftText} />
      </div>

      {result && (
        <section className="desk-section">
          <h2 className="desk-section-title">Результат</h2>
          <p className="desk-prose">
            {result.in_voice ? 'В голосе' : 'Выбивается'} — {result.voice_notes}
          </p>
          <textarea
            className="desk-textarea"
            value={revised}
            onChange={(e) => setRevised(e.target.value)}
            rows={8}
          />
          <CharCounter text={revised} />
          <CopyButton text={revised} />
          {(result.alternative_openings ?? []).map((line, i) => (
            <p key={i} className="desk-list-item">
              · {line}
            </p>
          ))}
          {(result.edits ?? []).map((editItem, i) => (
            <details key={i} className="desk-card desk-card--fold">
              <summary>{editItem.explanation || `правка ${i + 1}`}</summary>
              <p className="muted">было</p>
              <p className="desk-prose">{editItem.original}</p>
              <p className="muted">стало</p>
              <p className="desk-prose">{editItem.revised}</p>
              {editItem.suggestion_id && (
                <div className="desk-actions">
                  <button type="button" className="text-btn" onClick={() => applyEdit(editItem.suggestion_id!, true)}>
                    взять
                  </button>
                  <button type="button" className="text-btn" onClick={() => applyEdit(editItem.suggestion_id!, false)}>
                    оставить как было
                  </button>
                </div>
              )}
            </details>
          ))}
          <WhyBlockView why={result.why} />
          {result.suggestion_id && <FeedbackButtons suggestionId={result.suggestion_id} />}
        </section>
      )}

      <PublishBlock message={revised || draftText} planItemId={planItemId} />
    </DeskPage>
  )
}
