import type { WhyBlock } from '../api/types'

export function WhyBlockView({ why }: { why?: WhyBlock | null }) {
  if (!why?.summary) return null
  const parts = [why.summary]
  if (why.seasonality) parts.push(String(why.seasonality))
  return <div className="tr-why">{parts.join(' · ')}</div>
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return <div className="empty-state">{children}</div>
}

export function CharCounter({ text, warnAt = 600, hardAt = 1500 }: { text: string; warnAt?: number; hardAt?: number }) {
  const n = text.length
  let cls = 'muted'
  if (n >= hardAt) cls = 'muted'
  else if (n >= warnAt) cls = 'muted'
  return <p className={cls} style={{ fontSize: '0.82rem', margin: '0.25rem 0' }}>{n} символов</p>
}
