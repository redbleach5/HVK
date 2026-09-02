import type { ChatThread } from '../api/types'

interface Props {
  threads: ChatThread[]
  activeId?: number
  disabled?: boolean
  onSelect: (id: number) => void
  onCreate: () => void
  onDelete: (id: number) => void
  creating?: boolean
}

export function ChatThreadBar({
  threads,
  activeId,
  disabled,
  onSelect,
  onCreate,
  onDelete,
  creating,
}: Props) {
  return (
    <div className="chat-thread-bar">
      <div className="chat-thread-scroll">
        {threads.map((thread) => {
          const active = thread.id === activeId
          return (
            <div key={thread.id} className={`chat-thread-item${active ? ' chat-thread-item--active' : ''}`}>
              <button
                type="button"
                className="chat-thread-btn"
                onClick={() => onSelect(thread.id)}
                disabled={disabled}
                title={thread.title}
              >
                <span className="chat-thread-title">{thread.title}</span>
                {thread.message_count > 0 ? (
                  <span className="chat-thread-count">{thread.message_count}</span>
                ) : null}
              </button>
              <button
                type="button"
                className="chat-thread-delete"
                onClick={() => onDelete(thread.id)}
                disabled={disabled}
                aria-label={`Удалить «${thread.title}»`}
                title="удалить диалог"
              >
                ×
              </button>
            </div>
          )
        })}
      </div>
      <button
        type="button"
        className="chat-thread-new"
        onClick={onCreate}
        disabled={disabled || creating}
      >
        {creating ? '…' : '+ новый'}
      </button>
    </div>
  )
}
