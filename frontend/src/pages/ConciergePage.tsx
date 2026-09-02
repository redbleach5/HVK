import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiGet, apiPost, friendlyMessage } from '../api/client'
import type { ConciergeReply, InboxOut } from '../api/types'
import { CopyButton } from '../components/CopyButton'
import { DeskPage } from '../components/DeskPage'
import { useUiStore } from '../store/ui'

export function ConciergePage() {
  const { showToast } = useUiStore()
  const [message, setMessage] = useState('')
  const [reply, setReply] = useState<ConciergeReply | null>(null)

  const inboxQuery = useQuery({
    queryKey: ['concierge', 'inbox'],
    queryFn: () => apiGet<InboxOut>('/concierge/inbox'),
  })

  const draft = async () => {
    if (!message.trim()) return
    try {
      const out = await apiPost<ConciergeReply>('/concierge', { message_text: message.trim() })
      setReply(out)
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  return (
    <DeskPage title="ЛС" subtitle="Черновик ответа. Отправка только вручную в VK.">
      {inboxQuery.data?.available && (inboxQuery.data.items ?? []).length > 0 && (
        <section className="desk-section">
          <h2 className="desk-section-title">Входящие</h2>
          {inboxQuery.data.items.map((item) => (
            <div key={item.peer_id} className="desk-card">
              <p className="desk-prose">{item.preview}</p>
              <button type="button" className="text-btn" onClick={() => setMessage(item.preview)}>
                ответить
              </button>
            </div>
          ))}
        </section>
      )}

      <textarea
        className="desk-textarea"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        rows={6}
        placeholder="Вставь текст ЛС"
      />
      <div className="desk-actions">
        <button type="button" className="btn btn-primary" onClick={draft}>
          подготовить черновик
        </button>
      </div>

      {reply && (
        <div className="desk-card">
          <p className="muted">Тип: {reply.category_label || reply.category}</p>
          <p className="desk-prose">{reply.draft_reply}</p>
          <CopyButton text={reply.draft_reply} />
        </div>
      )}
    </DeskPage>
  )
}
