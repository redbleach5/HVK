import { Suspense, lazy, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { apiGet } from './api/client'
import type { OnboardingStatus } from './api/types'
import { Toast } from './components/Toast'
import { Shell } from './layout/Shell'
import { ChatPage } from './pages/ChatPage'
import { OnboardingPage } from './pages/OnboardingPage'

const TodayPage = lazy(() => import('./pages/TodayPage').then((m) => ({ default: m.TodayPage })))
const PhotoPage = lazy(() => import('./pages/PhotoPage').then((m) => ({ default: m.PhotoPage })))
const TextPage = lazy(() => import('./pages/TextPage').then((m) => ({ default: m.TextPage })))
const IdeasPage = lazy(() => import('./pages/IdeasPage').then((m) => ({ default: m.IdeasPage })))
const AnalyticsPage = lazy(() =>
  import('./pages/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage })),
)
const ConciergePage = lazy(() =>
  import('./pages/ConciergePage').then((m) => ({ default: m.ConciergePage })),
)

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

function PageFallback() {
  return <p className="muted desk-loading">Загрузка…</p>
}

function AppRoutes() {
  const [onboardingDone, setOnboardingDone] = useState<boolean | null>(null)

  const statusQuery = useQuery({
    queryKey: ['onboarding', 'status'],
    queryFn: () => apiGet<OnboardingStatus>('/onboarding/status'),
    enabled: onboardingDone === null,
  })

  const done = onboardingDone ?? statusQuery.data?.done ?? false

  if (onboardingDone === null && statusQuery.isLoading) {
    return <p className="muted" style={{ padding: '2rem' }}>Загрузка…</p>
  }

  if (!done) {
    return <OnboardingPage onComplete={() => setOnboardingDone(true)} />
  }

  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<ChatPage />} />
          <Route path="chat/:threadId" element={<ChatPage />} />
          <Route path="desk/today" element={<TodayPage />} />
          <Route path="desk/photo" element={<PhotoPage />} />
          <Route path="desk/text" element={<TextPage />} />
          <Route path="desk/ideas" element={<IdeasPage />} />
          <Route path="desk/analytics" element={<AnalyticsPage />} />
          <Route path="desk/concierge" element={<ConciergePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
        <Toast />
      </BrowserRouter>
    </QueryClientProvider>
  )
}
