import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, friendlyMessage } from '../api/client'
import type { HealthStatus, OnboardingStatus } from '../api/types'
import { ArchivePasteWidget } from '../components/ArchivePasteWidget'
import { OnboardingProgress } from '../components/OnboardingProgress'
import { useUiStore } from '../store/ui'

interface Props {
  onComplete: () => void
}

export function OnboardingPage({ onComplete }: Props) {
  const { showToast } = useUiStore()
  const queryClient = useQueryClient()
  const [blogName, setBlogName] = useState('')
  const [about, setAbout] = useState('')

  const statusQuery = useQuery({
    queryKey: ['onboarding', 'status'],
    queryFn: () => apiGet<OnboardingStatus>('/onboarding/status'),
  })

  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: () => apiGet<HealthStatus>('/health'),
  })

  const status = statusQuery.data
  if (!status) return <p className="muted">Загрузка…</p>

  if (status.done) {
    onComplete()
    return null
  }

  const step = status.step || 0
  const postsN = status.posts_imported || 0
  const vkOk = healthQuery.data?.vk_configured

  const saveProfile = async () => {
    try {
      await apiPost('/onboarding/profile', {
        blog_name: blogName || status.blog_name || 'Красивое в обычном',
        about: about || status.about,
      })
      await queryClient.invalidateQueries({ queryKey: ['onboarding', 'status'] })
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  const importVk = async () => {
    try {
      await apiPost('/onboarding/import-vk')
      showToast('Посты загружены. Голос дособирается тихо 🤍')
      await queryClient.invalidateQueries({ queryKey: ['onboarding', 'status'] })
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  const rebuildVoice = async () => {
    try {
      await apiPost('/onboarding/rebuild-voice')
      showToast('Голос пересобирается — загляни через минуту')
      await queryClient.invalidateQueries({ queryKey: ['onboarding', 'status'] })
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  const complete = async () => {
    try {
      await apiPost('/onboarding/complete')
      await queryClient.invalidateQueries({ queryKey: ['onboarding', 'status'] })
      onComplete()
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  return (
    <div style={{ maxWidth: 640, margin: '0 auto', padding: '2rem 1rem' }}>
      <h1 style={{ fontFamily: 'Source Serif 4, Georgia, serif', fontWeight: 500 }}>Тихая редакция</h1>
      <p className="muted">Три шага. Потом — диалог, как привычный чат. Стол слева, без настроек.</p>
      <OnboardingProgress step={step > 0 ? step : 1} />

      {step < 1 && (
        <>
          <h2>1. О блоге</h2>
          <label>
            Название
            <input
              style={{ display: 'block', width: '100%', margin: '0.35rem 0 0.75rem', padding: '0.5rem' }}
              value={blogName || status.blog_name}
              onChange={(e) => setBlogName(e.target.value)}
            />
          </label>
          <label>
            Кратко о себе
            <textarea
              style={{ display: 'block', width: '100%', margin: '0.35rem 0 0.75rem', padding: '0.5rem' }}
              rows={4}
              value={about || status.about}
              onChange={(e) => setAbout(e.target.value)}
              placeholder="Темы, тон, что обычно постишь"
            />
          </label>
          <button type="button" className="btn btn-primary" onClick={saveProfile}>
            дальше
          </button>
        </>
      )}

      {step >= 1 && step < 2 && (
        <>
          <h2>2. Покажи свой голос</h2>
          <p>
            Нужны твои посты в памяти — так я узнаю голос и сообщество. Без них диалог будет угадайкой.
          </p>
          {vkOk ? (
            <>
              <p className="muted">В архиве: {postsN} постов</p>
              <button type="button" className="btn btn-primary" onClick={importVk}>
                загрузить посты со стены VK
              </button>
              <details style={{ marginTop: '1rem' }}>
                <summary>Или вставить тексты вручную</summary>
                <ArchivePasteWidget />
              </details>
            </>
          ) : (
            <>
              <p>VK пока не подключён — вставь 3–8 своих постов.</p>
              <ArchivePasteWidget />
            </>
          )}
          {postsN >= 2 && (
            <button type="button" className="btn btn-primary" style={{ marginTop: '1rem' }} onClick={rebuildVoice}>
              дальше →
            </button>
          )}
        </>
      )}

      {step >= 2 && (
        <>
          <h2>3. Готово</h2>
          <p>Дальше — диалог. Слева тихий стол, когда нужен экран.</p>
          {status.voice_ready ? (
            <p>🤍 Голос собран — идеи и редактура будут опираться на твои тексты</p>
          ) : postsN > 0 ? (
            <p>
              Тексты уже в памяти ({postsN} постов). Голос дособирается — можно открывать, но первые идеи
              могут быть без голоса.
            </p>
          ) : (
            <ArchivePasteWidget />
          )}
          {postsN >= 2 ? (
            <button type="button" className="btn btn-primary" onClick={complete}>
              открыть
            </button>
          ) : (
            <p className="muted">Открою диалог, когда в памяти будут хотя бы два твоих поста.</p>
          )}
        </>
      )}
    </div>
  )
}
