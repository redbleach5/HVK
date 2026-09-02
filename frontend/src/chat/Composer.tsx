import { useEffect, useRef, useState } from 'react'
import { useUiStore } from '../store/ui'

const CHAT_MAX_CHARS = 48_000
const CHAT_WARN_CHARS = 40_000

interface Props {
  onSend: (text: string, files: File[]) => void
  disabled?: boolean
  initialValue?: string
}

export function Composer({ onSend, disabled, initialValue = '' }: Props) {
  const { showToast } = useUiStore()
  const [text, setText] = useState(initialValue)
  const [files, setFiles] = useState<File[]>([])
  const [previews, setPreviews] = useState<string[]>([])
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setText(initialValue)
  }, [initialValue])

  useEffect(() => {
    const urls = files.map((f) => URL.createObjectURL(f))
    setPreviews(urls)
    return () => {
      urls.forEach((u) => URL.revokeObjectURL(u))
    }
  }, [files])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 192)}px`
  }, [text])

  const submit = () => {
    const trimmed = text.trim()
    if (!trimmed && files.length === 0) return
    if (trimmed.length > CHAT_MAX_CHARS) {
      showToast('Слишком длинный текст — сократи или разбей на части.')
      return
    }
    onSend(trimmed, files)
    setText('')
    setFiles([])
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!disabled) submit()
    }
  }

  const onFiles = (list: FileList | null) => {
    if (!list) return
    setFiles((prev) => [...prev, ...Array.from(list)].slice(0, 8))
  }

  const canSend = !disabled && (text.trim().length > 0 || files.length > 0)
  const overLimit = text.length > CHAT_MAX_CHARS
  const warnLong = text.length > CHAT_WARN_CHARS && !overLimit

  return (
    <div className="composer-wrap">
      {files.length > 0 && (
        <div className="composer-attachments">
          {files.map((f, i) => (
            <div key={`${f.name}-${i}`} className="composer-attachment">
              {previews[i] ? <img src={previews[i]} alt="" /> : null}
              <button
                type="button"
                className="composer-attachment-remove"
                onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                aria-label="убрать фото"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="composer-pill">
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          className="composer-file-input"
          onChange={(e) => {
            onFiles(e.target.files)
            e.target.value = ''
          }}
        />
        <button
          type="button"
          className="composer-icon-btn"
          onClick={() => fileRef.current?.click()}
          disabled={disabled}
          title="Прикрепить фото"
          aria-label="Прикрепить фото"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
            <rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="1.75" />
            <circle cx="8.5" cy="10" r="1.5" fill="currentColor" />
            <path d="M21 16l-5-5-4 4-2-2-5 5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>

        <textarea
          ref={textareaRef}
          className="composer-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Напиши сообщение…"
          disabled={disabled}
          rows={1}
        />

        <button
          type="button"
          className={`composer-send${canSend && !overLimit ? ' composer-send--ready' : ''}`}
          disabled={!canSend || overLimit}
          onClick={submit}
          aria-label="Отправить"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M12 19V5M5 12l7-7 7 7"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>

      <p className="composer-hint">
        Enter — отправить · Shift+Enter — новая строка
        {warnLong ? ' · длинный текст — лучше сократить' : null}
        {overLimit ? ' · слишком длинно для одного сообщения' : null}
      </p>
    </div>
  )
}
