import { useState } from 'react'
import { apiPostFiles, friendlyMessage } from '../api/client'
import type { PhotoAnalysis } from '../api/types'
import { CopyButton } from '../components/CopyButton'
import { DeskPage } from '../components/DeskPage'
import { FeedbackButtons } from '../components/FeedbackButtons'
import { WhyBlockView } from '../components/Shared'
import { useDesk } from '../hooks/useDesk'
import { useUiStore } from '../store/ui'

const LABELS: [string, string][] = [
  ['atmosphere', 'атмосфера'],
  ['composition', 'композиция'],
  ['light', 'свет'],
  ['palette', 'палитра'],
  ['storytelling', 'история'],
  ['aesthetic_fit', 'в эстетике'],
]

export function PhotoPage() {
  const { showToast } = useUiStore()
  const { rememberDraft } = useDesk()
  const [files, setFiles] = useState<File[]>([])
  const [result, setResult] = useState<PhotoAnalysis | null>(null)
  const [loading, setLoading] = useState(false)

  const analyze = async () => {
    if (!files.length) return
    setLoading(true)
    try {
      const out = await apiPostFiles<PhotoAnalysis>('/photo/analyze', files)
      setResult(out)
    } catch (exc) {
      showToast(friendlyMessage(exc))
    } finally {
      setLoading(false)
    }
  }

  return (
    <DeskPage title="Фото" subtitle="Разбор кадра или серии">
      <div className="desk-upload-zone">
        <input
          className="desk-file-input"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          id="photo-upload"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
        <label htmlFor="photo-upload" className="desk-file-label">
          {files.length ? `Выбрано: ${files.length}` : 'выбрать фото'}
        </label>
      </div>

      {files.length > 0 && (
        <div className="composer-attachments">
          {files.map((f, i) => (
            <div key={i} className="composer-attachment">
              <img src={URL.createObjectURL(f)} alt="" />
            </div>
          ))}
        </div>
      )}

      <div className="desk-actions">
        <button type="button" className="btn btn-primary" disabled={!files.length || loading} onClick={analyze}>
          {loading ? 'смотрю…' : 'разобрать'}
        </button>
        {result && (
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setResult(null)
              setFiles([])
            }}
          >
            другой кадр
          </button>
        )}
      </div>

      {result && (
        <section className="desk-section">
          <h2 className="desk-section-title">{result.verdict}</h2>
          <div className="metrics-row">
            {LABELS.map(([key, label]) => (
              <div key={key} className="metric">
                <div className="metric-label">{label}</div>
                <div className="metric-value">{result.scores?.[key] ?? '—'}</div>
              </div>
            ))}
          </div>
          {result.series_comparison && <p className="desk-card desk-prose">{result.series_comparison}</p>}
          <p className="desk-prose">
            <strong>Направление для подписи:</strong> {result.caption_direction || '—'}
          </p>
          <CopyButton text={result.caption_direction} label="скопировать подпись" />
          <WhyBlockView why={result.why} />
          {result.suggestion_id && <FeedbackButtons suggestionId={result.suggestion_id} />}
          {(result.advice_suggestions ?? []).map((adv, i) => (
            <div key={i}>
              <p className="desk-list-item">· {adv.text}</p>
              {adv.suggestion_id && <FeedbackButtons suggestionId={adv.suggestion_id} />}
            </div>
          ))}
          <button
            type="button"
            className="text-btn"
            onClick={() => rememberDraft(result.caption_direction || result.verdict)}
          >
            набросать подпись
          </button>
        </section>
      )}
    </DeskPage>
  )
}
