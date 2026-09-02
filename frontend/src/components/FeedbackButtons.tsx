import { useState } from 'react'
import { apiPost, friendlyMessage } from '../api/client'
import { useUiStore } from '../store/ui'

interface Props {
  suggestionId: number
}

export function FeedbackButtons({ suggestionId }: Props) {
  const { showToast } = useUiStore()
  const [done, setDone] = useState<'yes' | 'no' | null>(null)

  const submit = async (accepted: boolean) => {
    try {
      await apiPost(`/feedback/${suggestionId}`, { accepted, note: '' })
      setDone(accepted ? 'yes' : 'no')
      showToast(accepted ? 'Учтено 🤍' : 'Запомнила — не моё')
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  if (done) {
    return (
      <p className="feedback-done">{done === 'yes' ? 'учтено' : 'запомнила — не моё'}</p>
    )
  }

  return (
    <div className="feedback-row">
      <button type="button" className="text-btn" disabled={done === 'yes'} onClick={() => submit(true)}>
        учту
      </button>
      <span className="feedback-sep">·</span>
      <button type="button" className="text-btn" disabled={done === 'no'} onClick={() => submit(false)}>
        не соглашусь
      </button>
    </div>
  )
}
