import type { LocalMessage } from '../store/ui'
import { CardRenderer } from './cards/CardRenderer'
import { MessageContent } from './MessageContent'
import { ThinkingBlock } from './ThinkingBlock'
import { FeedbackButtons } from '../components/FeedbackButtons'

interface Props {
  message: LocalMessage
  interactive: boolean
}

export function MessageBubble({ message, interactive }: Props) {
  const isUser = message.role === 'user'
  const cards = message.cards ?? []
  const rest = cards.filter((c) => c.type !== 'thinking')
  const covered = new Set<number>()
  const showAssistantBody = isUser || Boolean(message.content) || Boolean(message.streaming)

  for (const card of rest) {
    if (card.suggestion_id) covered.add(card.suggestion_id)
  }

  return (
    <div
      className={`message-row message-row--${message.role}`}
      data-message-role={message.role}
      data-streaming={!isUser && message.streaming ? 'true' : 'false'}
    >
      <div className="message-inner">
        {!isUser && message.streaming && message.thinking !== undefined && (
          <ThinkingBlock
            text={message.thinking}
            live={!message.content}
            collapsed={Boolean(message.content && message.thinking)}
          />
        )}
        {showAssistantBody && (
          <MessageContent
            content={message.content}
            role={message.role}
            streaming={Boolean(message.streaming && !isUser)}
          />
        )}
        {!message.streaming &&
          cards
            .filter((c) => c.type === 'thinking')
            .map((c, j) => <ThinkingBlock key={`think-${j}`} text={c.body} collapsed />)
        }
        {!isUser && !message.streaming &&
          rest.map((card, j) => (
            <CardRenderer key={`${message.id}-card-${j}`} card={card} interactive={interactive} />
          ))}
        {interactive && !message.streaming &&
          (message.suggestion_ids ?? []).map((sid) => {
            if (!sid || covered.has(sid)) return null
            return <FeedbackButtons key={sid} suggestionId={sid} />
          })}
      </div>
    </div>
  )
}
