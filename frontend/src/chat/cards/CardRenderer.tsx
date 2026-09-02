import { apiPost, friendlyMessage } from '../../api/client'
import type { ChatCard } from '../../api/types'
import { CopyButton } from '../../components/CopyButton'
import { FeedbackButtons } from '../../components/FeedbackButtons'
import { useDesk } from '../../hooks/useDesk'
import { useChatStore, useUiStore } from '../../store/ui'

interface Props {
  card: ChatCard
  interactive: boolean
}

export function CardRenderer({ card, interactive }: Props) {
  const { showToast } = useUiStore()
  const setPrefill = useChatStore((s) => s.setPrefill)
  const { rememberDraft, rememberPlan } = useDesk()
  const ctype = card.type
  const data = card.data ?? {}
  const sid = card.suggestion_id

  const toPlanIdea = async (ideaId: unknown) => {
    if (!ideaId) return
    try {
      const item = await apiPost<{ id: number; title?: string }>(`/ideas/${ideaId}/to-plan`)
      await rememberPlan(item.id)
      showToast('В плане')
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  const toPlanText = async (title: string, draft = '') => {
    try {
      const item = await apiPost<{ id: number }>('/plan/from-text', {
        title: title.slice(0, 240),
        draft_text: draft,
      })
      await rememberPlan(item.id)
      showToast('В плане')
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  if (ctype === 'web') {
    const short = (card.body || '').replace(/\s+/g, ' ').trim()
    const line = [card.title || 'из поиска', short.length > 160 ? `${short.slice(0, 157)}…` : short]
      .filter(Boolean)
      .join(' · ')
    return <div className="tr-why">{line}</div>
  }

  if (ctype === 'why') {
    const short = (card.body || '').replace(/\s+/g, ' ').trim()
    const line = [card.title || 'из твоих текстов', short.length > 160 ? `${short.slice(0, 157)}…` : short]
      .filter(Boolean)
      .join(' · ')
    return (
      <div>
        <div className="tr-why">{line}</div>
          {interactive && Boolean(data.plan_title) && (
          <button type="button" className="text-btn" onClick={() => toPlanText(String(data.plan_title))}>
            в план
          </button>
        )}
        {interactive && sid && <FeedbackButtons suggestionId={sid} />}
      </div>
    )
  }

  return (
    <div className="card-inline">
      {card.title && <p className="card-inline-title">{card.title}</p>}
      {card.body && <p className="card-inline-body">{card.body}</p>}

      {ctype === 'idea' && (
        <>
          <p className="muted">
            {[data.format, data.effort ? `усилие: ${data.effort}` : '', data.why_now]
              .filter(Boolean)
              .join(' · ')}
          </p>
          <div className="card-actions">
          {interactive && Boolean(data.id) && (
            <button type="button" className="text-btn" onClick={() => toPlanIdea(data.id)}>
              в план
            </button>
          )}
          {interactive && Boolean(data.personal_angle || data.description) && (
            <button
              type="button"
              className="text-btn"
              onClick={() =>
                rememberDraft(
                  `${card.title}\n\n${data.personal_angle || ''}\n\n${data.description || card.body}`,
                )
              }
            >
              в черновик
            </button>
          )}
          </div>
        </>
      )}

      {ctype === 'edit' && (
        <>
          {Array.isArray(data.openings) &&
            (data.openings as string[]).slice(0, 4).map((line, i) => <p key={i}>· {line}</p>)}
          {interactive && (
            <div className="card-actions">
              <button
                type="button"
                className="text-btn"
                onClick={() =>
                  setPrefill(`опубликовать: ${data.revised_text || card.body}\n\nподтверждаю`)
                }
              >
                опубликовать
              </button>
              <CopyButton text={String(data.revised_text || card.body)} />
            </div>
          )}
        </>
      )}

      {ctype === 'photo' && (
        <>
          {data.scores && typeof data.scores === 'object' && (
            <div className="metrics-row">
              {Object.entries(data.scores as Record<string, number>).map(([k, v]) => (
                <div key={k} className="metric">
                  <div className="metric-label">{k}</div>
                  <div className="metric-value">{v}</div>
                </div>
              ))}
            </div>
          )}
          {interactive && data.caption_direction && (
            <button
              type="button"
              className="text-btn"
              onClick={() => rememberDraft(String(data.caption_direction))}
            >
              в черновик
            </button>
          )}
        </>
      )}

      {ctype === 'concierge' && (
        <>
          <p className="muted">Отправь сама в VK — система ничего не шлёт.</p>
          {data.draft_reply && <CopyButton text={String(data.draft_reply)} />}
        </>
      )}

      {ctype === 'inbox' && interactive && card.body && (
        <button type="button" className="text-btn" onClick={() => setPrefill(`ответь на: ${card.body}`)}>
          ответить на это
        </button>
      )}

      {ctype === 'archive' && interactive && (
        <button type="button" className="text-btn" onClick={() => toPlanText(card.title || 'Из архива', card.body)}>
          в план
        </button>
      )}

      {interactive && sid && ctype !== 'why' && (
        <FeedbackButtons suggestionId={sid} />
      )}
    </div>
  )
}
