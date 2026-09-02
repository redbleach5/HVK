import { test, expect } from '@playwright/test'

async function onboardingDone(request: import('@playwright/test').APIRequestContext) {
  const res = await request.get('/api/onboarding/status')
  expect(res.ok()).toBeTruthy()
  const body = (await res.json()) as { done?: boolean }
  return Boolean(body.done)
}

test.describe('HVK SPA smoke', () => {
  test('home loads', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('#root')).toBeVisible()

    const composer = page.getByPlaceholder('Напиши сообщение…')
    const onboarding = page.getByRole('heading', { level: 1, name: 'Тихая редакция' })
    await expect(composer.or(onboarding)).toBeVisible()
  })

  test('API proxy from browser', async ({ page }) => {
    await page.goto('/')
    const health = await page.evaluate(async () => {
      const r = await fetch('/api/health')
      return { status: r.status, ok: r.ok }
    })
    expect(health.status).toBe(200)
    expect(health.ok).toBe(true)
  })
})

test.describe('chat shell', () => {
  test.beforeEach(async ({ request }) => {
    test.skip(!(await onboardingDone(request)), 'onboarding not complete')
  })

  test('composer and sidebar', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByPlaceholder('Напиши сообщение…')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Чат' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Сегодня' })).toBeVisible()
  })

  test('quick chips when chat empty', async ({ page, request }) => {
    const hist = await request.get('/api/chat/history')
    expect(hist.ok()).toBeTruthy()
    const body = (await hist.json()) as { messages?: unknown[] }
    test.skip((body.messages?.length ?? 0) > 0, 'chat history not empty')

    await page.goto('/')
    await expect(page.getByText('Чем помочь сегодня?')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Что сегодня?' })).toBeVisible()
  })

  test('composer enables send', async ({ page }) => {
    await page.goto('/')
    await page.getByPlaceholder('Напиши сообщение…').fill('тест')
    await expect(page.getByRole('button', { name: 'Отправить' })).toBeEnabled()
  })

  test('sidebar desk navigation', async ({ page }) => {
    await page.goto('/')

    const desks = ['Сегодня', 'Фото', 'Текст', 'Идеи и план', 'Аналитика'] as const
    for (const label of desks) {
      await page.getByRole('link', { name: label, exact: true }).click()
      await expect(page.getByRole('heading', { level: 1, name: label })).toBeVisible()
      await expect(page.locator('.desk-loading')).toHaveCount(0)
    }

    await page.getByRole('link', { name: 'Чат', exact: true }).click()
    await expect(page.getByPlaceholder('Напиши сообщение…')).toBeVisible()
  })
})
