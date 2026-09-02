import { useEffect, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type { LocalMessage } from '../store/ui'
import { MessageBubble } from './MessageBubble'

interface Props {
  messages: LocalMessage[]
}

function PlainMessageList({ messages }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    ref.current?.querySelector('[data-chat-end]')?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="message-list" ref={ref}>
      {messages.map((msg, i) => (
        <MessageBubble
          key={msg.id}
          message={msg}
          interactive={msg.role === 'assistant' && i === messages.length - 1}
        />
      ))}
      <div data-chat-end />
    </div>
  )
}

function VirtualMessageList({ messages }: Props) {
  const parentRef = useRef<HTMLDivElement>(null)

  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 140,
    overscan: 8,
  })

  useEffect(() => {
    if (!messages.length) return
    virtualizer.scrollToIndex(messages.length - 1, { align: 'end', behavior: 'smooth' })
  }, [messages, virtualizer])

  return (
    <div className="message-list message-list--virtual" ref={parentRef}>
      <div className="message-list-virtual-inner" style={{ height: `${virtualizer.getTotalSize()}px` }}>
        {virtualizer.getVirtualItems().map((item) => {
          const msg = messages[item.index]
          return (
            <div
              key={msg.id}
              className="message-list-virtual-item"
              data-index={item.index}
              ref={virtualizer.measureElement}
              style={{ transform: `translateY(${item.start}px)` }}
            >
              <MessageBubble
                message={msg}
                interactive={msg.role === 'assistant' && item.index === messages.length - 1}
              />
            </div>
          )
        })}
      </div>
      <div data-chat-end />
    </div>
  )
}

const VIRTUALIZE_AFTER = 40

export function MessageList({ messages }: Props) {
  if (messages.length > VIRTUALIZE_AFTER) {
    return <VirtualMessageList messages={messages} />
  }
  return <PlainMessageList messages={messages} />
}
