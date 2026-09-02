export function CopyButton({ text, label = 'копировать' }: { text: string; label?: string }) {
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      /* ignore */
    }
  }
  if (!text.trim()) return null
  return (
    <button type="button" className="text-btn" onClick={copy}>
      {label}
    </button>
  )
}
