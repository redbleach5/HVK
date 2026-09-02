import { useState } from 'react'
import { apiPost, friendlyMessage } from '../api/client'
import { useUiStore } from '../store/ui'

interface Props {
  minBlocks?: number
}

export function ArchivePasteWidget({ minBlocks = 2 }: Props) {
  const { showToast } = useUiStore()
  const [pasted, setPasted] = useState('')
  const [saving, setSaving] = useState(false)

  const save = async () => {
    const blocks = pasted.split('\n\n').map((b) => b.trim()).filter(Boolean)
    if (blocks.length < minBlocks) {
      showToast(
        minBlocks > 1
          ? 'Нужно хотя бы два блока — так я лучше чувствую голос.'
          : 'Нужен хотя бы один пост.',
      )
      return
    }
    setSaving(true)
    try {
      await apiPost('/onboarding/archive', { posts: blocks })
      showToast('Тексты в памяти. Голос дособирается тихо 🤍')
      setPasted('')
    } catch (exc) {
      showToast(friendlyMessage(exc))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <textarea
        value={pasted}
        onChange={(e) => setPasted(e.target.value)}
        placeholder={'Пост 1:\n...\n\nПост 2:\n...'}
        rows={8}
        style={{ width: '100%', marginBottom: '0.5rem' }}
      />
      <button type="button" className="btn btn-primary" disabled={saving} onClick={save}>
        сохранить в память
      </button>
    </div>
  )
}
