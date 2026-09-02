import ReactMarkdown from 'react-markdown'

interface Props {
  content: string
  role: 'user' | 'assistant'
  streaming?: boolean
}

export function MessageContent({ content, role, streaming }: Props) {
  if (role === 'user') {
    return <div className="message-body message-body--user">{content}</div>
  }

  if (streaming) {
    return (
      <div className="message-body message-body--assistant message-body--streaming">
        {content ? <span className="message-stream-text">{content}</span> : null}
        <span className="stream-cursor" aria-hidden="true" />
      </div>
    )
  }

  if (!content) return null

  return (
    <div className="message-body message-body--assistant prose">
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  )
}
