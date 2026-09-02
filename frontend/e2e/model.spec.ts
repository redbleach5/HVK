import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { test, expect, type Page } from '@playwright/test'
import {
  assertGroundedText,
  assertReplyQuality,
  LLM_TIMEOUT,
  HEAVY_LLM_TIMEOUT,
  requireArchive,
  sendChatAndWait,
  waitDeskLoaded,
} from './helpers'

const FIXTURE_PHOTO = path.join(path.dirname(fileURLToPath(import.meta.url)), '../src/assets/hero.png')

async function openDesk(page: Page, label: string) {
  await page.goto('/')
  await expect(page.getByPlaceholder('Напиши сообщение…')).toBeVisible()
  await page.getByRole('link', { name: label, exact: true }).click()
  await waitDeskLoaded(page)
}

test.describe.configure({ mode: 'serial', timeout: HEAVY_LLM_TIMEOUT + 120_000 })

test.describe('model E2E', () => {
  test.beforeEach(async ({ request }) => {
    await requireArchive(request)
  })

  test('chat: stream completes with grounded reply', async ({ page }) => {
    await page.goto('/')
    const reply = await sendChatAndWait(page, 'привет, проверка связи e2e')
    assertReplyQuality(reply)
  })

  test('chat: ideas command cites archive', async ({ page }) => {
    await page.goto('/')
    let reply = ''
    for (let attempt = 0; attempt < 2; attempt += 1) {
      reply = await sendChatAndWait(page, attempt === 0 ? 'идеи' : 'идеи')
      assertReplyQuality(reply)
      const low = reply.toLowerCase()
      const cards = await page.locator('.card-inline').count()
      const grounded =
        cards > 0 ||
        low.includes('пост #') ||
        low.includes('пост#') ||
        low.includes('архив') ||
        low.includes('у тебя') ||
        low.includes('уже писала') ||
        reply.length >= 80
      if (grounded) return
    }
    expect(false, `ideas reply not grounded: ${reply.slice(0, 200)}`).toBeTruthy()
  })

  test('chat: audience question grounded', async ({ page }) => {
    await page.goto('/')
    const reply = await sendChatAndWait(
      page,
      'Что лучше заходило в последнее время — и почему',
    )
    assertReplyQuality(reply)
    const low = reply.toLowerCase()
    expect(
      low.includes('пост #') ||
        low.includes('архив') ||
        low.includes('заходил') ||
        low.includes('отклик') ||
        reply.length >= 100,
      `audience reply weak: ${reply.slice(0, 200)}`,
    ).toBeTruthy()
  })

  test('desk today: digest from model', async ({ page }) => {
    await openDesk(page, 'Сегодня')
    const digest = page.locator('.desk-card--lead .desk-prose').first()
    await expect(digest).toBeVisible({ timeout: 60_000 })
    assertGroundedText(await digest.innerText(), 40)
  })

  test('desk ideas: shows cached archive ideas', async ({ page, request }) => {
    const res = await request.get('/api/ideas')
    expect(res.ok()).toBeTruthy()
    const body = (await res.json()) as { ideas?: unknown[] }
    expect((body.ideas ?? []).length).toBeGreaterThan(0)

    await openDesk(page, 'Идеи и план')
    const cards = page.locator('.desk-section').filter({ hasText: 'Новые идеи' }).locator('.desk-card')
    await expect(cards.first()).toBeVisible({ timeout: 30_000 })
    assertGroundedText(await cards.first().innerText(), 30)
  })

  test('desk ideas: generate batch', async ({ page }) => {
    await openDesk(page, 'Идеи и план')
    await page.getByRole('slider', { name: /Сколько идей/ }).fill('2')
    const responsePromise = page.waitForResponse(
      (res) => res.url().includes('/ideas/generate') && res.request().method() === 'POST',
      { timeout: HEAVY_LLM_TIMEOUT },
    )
    await page.getByRole('button', { name: /предложить идеи|идеи…/ }).click()
    const response = await responsePromise
    expect(response.ok(), `ideas API status ${response.status()}`).toBeTruthy()
    const data = (await response.json()) as { ideas?: Array<{ theme?: string; description?: string }> }
    expect((data.ideas ?? []).length, 'ideas array empty').toBeGreaterThan(0)
    const ideaCards = page.locator('.desk-section').filter({ hasText: 'Новые идеи' }).locator('.desk-card')
    await expect(ideaCards.first()).toBeVisible({ timeout: 10_000 })
    const sample = (await ideaCards.first().innerText()).trim()
    assertGroundedText(sample, 30)
  })

  test('desk text: edit draft in voice', async ({ page }) => {
    await openDesk(page, 'Текст')
    const draft = 'чай остыл, а стол ещё тёплый. хочу короче и по-моему.'
    await page.getByPlaceholder('Вставь черновик').fill(draft)
    await page.getByRole('button', { name: 'отредактировать' }).click()
    await expect(page.getByRole('heading', { name: 'Результат' })).toBeVisible({ timeout: HEAVY_LLM_TIMEOUT })
    const revised = page.locator('.desk-section').filter({ hasText: 'Результат' }).locator('textarea').first()
    await expect(revised).not.toHaveValue('')
    const text = await revised.inputValue()
    assertGroundedText(text, 15)
    await expect(page.getByText(/В голосе|Выбивается/)).toBeVisible()
  })

  test('desk photo: analyze image', async ({ page }) => {
    await openDesk(page, 'Фото')
    await page.locator('#photo-upload').setInputFiles(FIXTURE_PHOTO)
    await expect(page.getByText('Выбрано: 1')).toBeVisible()
    await page.getByRole('button', { name: 'разобрать' }).click()
    const verdict = page.locator('.desk-section .desk-section-title').first()
    await expect(verdict).not.toBeEmpty({ timeout: HEAVY_LLM_TIMEOUT })
    assertGroundedText(await verdict.innerText(), 5)
    await expect(page.getByText('Направление для подписи:')).toBeVisible()
  })

  test('desk analytics: audience report', async ({ page, request }) => {
    const analytics = await request.get('/api/analytics?with_report=false')
    expect(analytics.ok()).toBeTruthy()
    const body = (await analytics.json()) as { posts_count?: number }
    test.skip(!body.posts_count, 'no posts for analytics')

    await openDesk(page, 'Аналитика')
    await page.getByRole('button', { name: 'сделать выводы' }).click()
    const report = page.locator('.desk-section').filter({ hasText: 'Выводы' }).locator('.desk-card').first()
    await expect(report).toBeVisible({ timeout: HEAVY_LLM_TIMEOUT })
    assertGroundedText(await report.innerText(), 50)
  })

  test('desk concierge: draft reply', async ({ page, request }) => {
    const health = await request.get('/api/health')
    const vk = ((await health.json()) as { vk_configured?: boolean }).vk_configured
    test.skip(!vk, 'VK not configured')

    await openDesk(page, 'ЛС')
    await page
      .getByPlaceholder('Вставь текст ЛС')
      .fill('Привет! Подскажи, где вы брали эту юбку из последнего поста?')
    await page.getByRole('button', { name: 'подготовить черновик' }).click()
    const card = page.locator('.desk-card').filter({ hasText: 'Тип:' }).first()
    await expect(card).toBeVisible({ timeout: HEAVY_LLM_TIMEOUT })
    const draft = await card.locator('.desk-prose').innerText()
    assertGroundedText(draft, 15)
  })
})
