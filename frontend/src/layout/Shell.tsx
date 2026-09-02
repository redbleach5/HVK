import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'

export function Shell() {
  const [navOpen, setNavOpen] = useState(false)

  return (
    <div className="app-shell">
      <header className="mobile-topbar">
        <button
          type="button"
          className="mobile-menu-btn"
          onClick={() => setNavOpen((v) => !v)}
          aria-label="Меню"
        >
          <span />
          <span />
          <span />
        </button>
        <span className="mobile-topbar-title">Тихая редакция</span>
      </header>

      {navOpen && (
        <button
          type="button"
          className="sidebar-overlay"
          aria-label="Закрыть меню"
          onClick={() => setNavOpen(false)}
        />
      )}

      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />

      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}
