import { useEffect } from 'react'
import { useUiStore } from '../store/ui'

export function Toast() {
  const { toast, clearToast } = useUiStore()

  useEffect(() => {
    if (!toast) return
    const t = window.setTimeout(clearToast, 2500)
    return () => window.clearTimeout(t)
  }, [toast, clearToast])

  if (!toast) return null
  return <div className="toast">{toast}</div>
}
