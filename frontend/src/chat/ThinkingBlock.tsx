interface Props {
  text: string
  collapsed?: boolean
  live?: boolean
}

export function ThinkingBlock({ text, collapsed, live }: Props) {
  if (collapsed && text) {
    return (
      <details className="tr-think tr-think--collapsed">
        <summary className="kicker">размышляю</summary>
        <p className="tr-think-body">{text}</p>
      </details>
    )
  }

  if (live && !text) {
    return (
      <div className="tr-think tr-think--live tr-think--wait">
        <p className="kicker">размышляю</p>
        <p className="tr-think-hint">
          собираю мысль
          <span className="stream-cursor stream-cursor--muted" aria-hidden="true" />
        </p>
      </div>
    )
  }

  if (!text && !live) {
    return (
      <div className="tr-think tr-think--wait">
        <p className="kicker">размышляю</p>
        <p className="tr-think-hint">собираю мысль — можно не торопиться</p>
      </div>
    )
  }

  return (
    <div className={`tr-think${live ? ' tr-think--live' : ''}`}>
      <p className="kicker">размышляю</p>
      <p className="tr-think-body">
        {text}
        {live && <span className="stream-cursor stream-cursor--muted" aria-hidden="true" />}
      </p>
    </div>
  )
}
