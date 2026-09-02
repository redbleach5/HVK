import type { ReactNode } from 'react'
import { DeskBack } from './DeskBack'

interface Props {
  title: string
  subtitle?: string
  children: ReactNode
}

export function DeskPage({ title, subtitle, children }: Props) {
  return (
    <div className="desk-page">
      <DeskBack />
      <header className="page-header">
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </header>
      {children}
    </div>
  )
}
