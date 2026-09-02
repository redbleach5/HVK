import { useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, friendlyMessage } from '../api/client'
import type { HealthStatus, OnboardingStatus } from '../api/types'
import { ArchivePasteWidget } from './ArchivePasteWidget'
import { useUiStore } from '../store/ui'

export function ArchiveBanner() {
  const { showToast } = useUiStore()
  const queryClient = useQueryClient()

  const statusQuery = useQuery({
    queryKey: ['onboarding', 'status'],
    queryFn: () => apiGet<OnboardingStatus>('/onboarding/status'),
  })

  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: () => apiGet<HealthStatus>('/health'),
  })

  const postsN = statusQuery.data?.posts_imported ?? 0
  if (postsN >= 2) return null

  const vkOk = healthQuery.data?.vk_configured ?? false

  const importVk = async () => {
    try {
      await apiPost('/onboarding/import-vk')
      showToast('Посты в памяти. Голос дособирается тихо 🤍')
      await queryClient.invalidateQueries({ queryKey: ['onboarding', 'status'] })
    } catch (exc) {
      showToast(friendlyMessage(exc))
    }
  }

  return (
    <div className="banner-warn">
      {vkOk ? (
        <>
          <p>
            В памяти ещё нет твоих постов. Загрузи со стены VK — так редакция узнает голос и
            сообщество.
          </p>
          <button type="button" className="btn btn-primary" onClick={importVk}>
            загрузить посты со стены VK
          </button>
          <details style={{ marginTop: '0.75rem' }}>
            <summary className="muted">Вставить тексты вручную</summary>
            <ArchivePasteWidget />
          </details>
        </>
      ) : (
        <>
          <p>
            Без твоих текстов я буду угадывать. Вставь 3–8 своих постов — про чай, стол, тихое утро
            — и редакция станет настоящей 🤍
          </p>
          <ArchivePasteWidget />
        </>
      )}
    </div>
  )
}
