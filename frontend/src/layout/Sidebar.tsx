import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { apiGet } from '../api/client'
import type { DeskPage, DiagnosticsOut, HealthStatus } from '../api/types'
import { DESK_LABELS } from '../api/types'

const DESK_PAGES: DeskPage[] = ['today', 'photo', 'text', 'ideas', 'analytics']

interface Props {
  open?: boolean
  onClose?: () => void
}

export function Sidebar({ open = true, onClose }: Props) {
  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: () => apiGet<HealthStatus>('/health'),
  })

  const voiceQuery = useQuery({
    queryKey: ['voice'],
    queryFn: () => apiGet('/voice'),
    retry: false,
  })

  const diagnosticsQuery = useQuery({
    queryKey: ['diagnostics'],
    queryFn: () =>
      apiGet<DiagnosticsOut>('/health/diagnostics', {
        probe: false,
        insight: false,
        refresh: true,
      }),
    refetchInterval: 5 * 60_000,
    staleTime: 4 * 60_000,
    retry: false,
  })

  const vkOk = healthQuery.data?.vk_configured
  const pages = vkOk ? [...DESK_PAGES, 'concierge' as DeskPage] : DESK_PAGES

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `side-link${isActive ? ' side-link--active' : ''}`

  const handleNav = () => onClose?.()

  return (
    <aside className={`sidebar${open ? ' sidebar--open' : ''}`}>
      <div className="sidebar-inner">
        <div className="tr-side-brand">Тихая редакция</div>
        <p className="tr-side-sub">ассистент, не автор</p>

        <p className="tr-side-label">Диалог</p>
        <NavLink to="/" className={linkClass} onClick={handleNav}>
          Чат
        </NavLink>

        <p className="tr-side-label">Стол</p>
        <nav className="side-nav">
          {pages.map((page) => (
            <NavLink
              key={page}
              to={`/desk/${page}`}
              className={linkClass}
              onClick={handleNav}
            >
              {DESK_LABELS[page]}
            </NavLink>
          ))}
        </nav>

        <p className="sidebar-foot">
          {voiceQuery.data ? 'голос собран' : 'голос появится с архивом'}
        </p>
        {diagnosticsQuery.data?.author_hint ? (
          <p className="sidebar-hint">{diagnosticsQuery.data.author_hint}</p>
        ) : null}
      </div>
    </aside>
  )
}
