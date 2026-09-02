import { useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArchiveBanner } from '../components/ArchiveBanner'
import { ChatThreadBar } from '../chat/ChatThreadBar'
import { Composer } from '../chat/Composer'
import { MessageList } from '../chat/MessageList'
import { useChat } from '../hooks/useChat'
import { useChatThreads } from '../hooks/useChatThreads'

const CHIPS = [
  ['Что сегодня?', 'сегодня'],
  ['Идеи', 'идеи'],
  ['Что заходило?', 'что лучше заходило в последнее время — и почему'],
  ['Помоги с текстом', 'хочу поправить текст'],
] as const

function parseThreadId(raw: string | undefined): number | undefined {
  if (!raw) return undefined
  const n = Number.parseInt(raw, 10)
  return Number.isFinite(n) ? n : undefined
}

export function ChatPage() {
  const navigate = useNavigate()
  const { threadId: threadParam } = useParams()
  const threadId = parseThreadId(threadParam)

  const { threads, createThread, deleteThread, isCreating, isDeleting } = useChatThreads()
  const {
    messages,
    isStreaming,
    prefill,
    setPrefill,
    sendMessage,
    clearHistory,
    historyLoading,
    activeThreadId,
  } = useChat(threadId)

  const resolvedId = threadId ?? activeThreadId
  const busy = isStreaming || isCreating || isDeleting

  const selectThread = useCallback(
    (id: number) => {
      if (id !== resolvedId) navigate(`/chat/${id}`)
    },
    [navigate, resolvedId],
  )

  const handleCreate = useCallback(async () => {
    const created = await createThread()
    navigate(`/chat/${created.id}`)
  }, [createThread, navigate])

  const handleDelete = useCallback(
    async (id: number) => {
      const idx = threads.findIndex((t) => t.id === id)
      const remaining = threads.filter((t) => t.id !== id)
      await deleteThread(id)
      if (id === resolvedId) {
        if (remaining.length > 0) {
          const next = remaining[Math.min(Math.max(idx, 0), remaining.length - 1)]
          navigate(`/chat/${next.id}`)
        } else {
          navigate('/')
        }
      }
    },
    [deleteThread, navigate, resolvedId, threads],
  )

  const empty = !historyLoading && messages.length === 0

  return (
    <div className="chat-page">
      <div className="chat-toolbar">
        <ArchiveBanner />
        <ChatThreadBar
          threads={threads}
          activeId={resolvedId}
          disabled={busy}
          onSelect={selectThread}
          onCreate={handleCreate}
          onDelete={handleDelete}
          creating={isCreating}
        />
        {!empty ? (
          <button type="button" className="text-btn" onClick={clearHistory} disabled={busy}>
            очистить сообщения
          </button>
        ) : null}
      </div>

      {empty ? (
        <div className="chat-empty">
          <div className="tr-chat-home">
            <div className="tr-chat-home-title">Тихая редакция</div>
            <p className="tr-chat-home-sub">Чем помочь сегодня?</p>
            <div className="chip-row">
              {CHIPS.map(([label, text]) => (
                <button
                  key={label}
                  type="button"
                  className="chip"
                  onClick={() => sendMessage(text)}
                  disabled={isStreaming}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <MessageList messages={messages} />
      )}

      {prefill && (
        <div className="tr-pending">
          <p className="kicker">черновик для отправки</p>
          <div className="tr-pending-body">{prefill.slice(0, 1200)}</div>
          <div className="pending-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => sendMessage(prefill)}
              disabled={isStreaming}
            >
              отправить
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setPrefill(null)}>
              отмена
            </button>
          </div>
        </div>
      )}

      <Composer onSend={sendMessage} disabled={isStreaming} />
    </div>
  )
}
