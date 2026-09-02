import { expect, type APIRequestContext, type Page } from '@playwright/test'

export interface OnboardingStatus {
  done?: boolean
  posts_imported?: number
  voice_ready?: boolean
}

const EMPTY_ARCHIVE_MARKERS = [
  'не читала твои тексты',
  'угадайка',
  'сначала нужны твои тексты',
  'с потолка',
  'без архива',
]

const ERROR_LEAK_MARKERS = [
  'что-то тихо не сложилось',
  'ollama',
  'traceback',
  '127.0.0.1',
  'localhost:',
  '.env',
]

const HUSBAND_JUDGMENT = ['муж должен', 'пусть поможет', 'он не помогает', 'тебе одной тяжело потому что он']

export const LLM_TIMEOUT = 900_000
export const HEAVY_LLM_TIMEOUT = 1_200_000

export async function getOnboardingStatus(request: APIRequestContext): Promise<OnboardingStatus> {
  const res = await request.get('/api/onboarding/status')
  expect(res.ok()).toBeTruthy()
  return (await res.json()) as OnboardingStatus
}

export async function requireOnboarding(request: APIRequestContext): Promise<OnboardingStatus> {
  const status = await getOnboardingStatus(request)
  expect(status.done, 'onboarding not complete').toBeTruthy()
  return status
}

export async function requireArchive(request: APIRequestContext): Promise<OnboardingStatus> {
  const status = await requireOnboarding(request)
  expect((status.posts_imported ?? 0) >= 2, 'archive too small').toBeTruthy()
  return status
}

export function assertGroundedText(text: string, minLen = 20) {
  const low = (text || '').toLowerCase().trim()
  expect(low.length, 'text too short').toBeGreaterThanOrEqual(minLen)
  for (const marker of EMPTY_ARCHIVE_MARKERS) {
    expect(low, `empty-archive: ${marker}`).not.toContain(marker)
  }
  for (const marker of ERROR_LEAK_MARKERS) {
    expect(low, `error leak: ${marker}`).not.toContain(marker)
  }
}

export function assertReplyQuality(reply: string) {
  assertGroundedText(reply, 8)
  const low = reply.toLowerCase()
  for (const marker of HUSBAND_JUDGMENT) {
    expect(low, `judges family: ${marker}`).not.toContain(marker)
  }
  expect(low.includes('юля') && low.includes('уснула'), 'invented julia sleep').toBeFalsy()
}

export async function sendChatAndWait(page: Page, message: string, timeoutMs = LLM_TIMEOUT): Promise<string> {
  const probe = message.includes('e2e-') ? message : `${message} · e2e-${Date.now()}`
  const composer = page.getByPlaceholder('Напиши сообщение…')
  await composer.fill(probe)
  await page.getByRole('button', { name: 'Отправить' }).click()

  await expect(page.locator('.message-row--user').filter({ hasText: probe }).last()).toBeVisible({
    timeout: 15_000,
  })

  const streaming = page.locator('[data-message-role="assistant"][data-streaming="true"]')
  await expect(streaming).toHaveCount(1, { timeout: 60_000 })
  await expect(streaming).toHaveCount(0, { timeout: timeoutMs })

  const row = page.locator('[data-message-role="assistant"]').last()
  const body = row.locator('.message-body--assistant').last()
  await expect(body).toBeVisible()
  const text = (await body.innerText()).trim()
  expect(text.length, 'assistant reply empty').toBeGreaterThan(0)
  return text
}

export async function waitDeskLoaded(page: Page) {
  await expect(page.locator('.desk-loading')).toHaveCount(0, { timeout: 60_000 })
}
