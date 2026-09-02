import type { StreamEvent } from './types'

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export class ApiError extends Error {
  statusCode: number | null

  constructor(message: string, statusCode: number | null = null) {
    super(message)
    this.name = 'ApiError'
    this.statusCode = statusCode
  }
}

function authorDetail(detail: unknown): string {
  if (Array.isArray(detail)) {
    return 'Что-то тихо не сложилось. Попробуй ещё раз.'
  }
  const text = String(detail ?? '').trim()
  if (!text) return 'Что-то тихо не сложилось. Попробуй ещё раз.'
  const low = text.toLowerCase()
  if (
    text.startsWith('{') ||
    text.startsWith('[') ||
    low.includes('traceback') ||
    low.includes('.env') ||
    low.includes('ollama') ||
    low.includes('gguf') ||
    low.includes('llama.cpp') ||
    low.includes('127.0.0.1') ||
    low.includes('localhost:')
  ) {
    return 'Что-то тихо не сложилось. Попробуй ещё раз.'
  }
  return text
}

async function handle<T>(response: Response): Promise<T> {
  if (response.status >= 400) {
    let detail: unknown = 'Что-то тихо не сложилось'
    try {
      const payload = await response.json()
      detail = payload.detail ?? detail
    } catch {
      detail = await response.text()
    }
    throw new ApiError(authorDetail(detail), response.status)
  }
  if (response.status === 204) return {} as T
  const text = await response.text()
  if (!text) return {} as T
  return JSON.parse(text) as T
}

function url(path: string, params?: Record<string, string | boolean | undefined>): string {
  const base = `${API_BASE}${path}`
  if (!params) return base
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) qs.set(k, String(v))
  }
  const q = qs.toString()
  return q ? `${base}?${q}` : base
}

export async function apiGet<T>(
  path: string,
  params?: Record<string, string | boolean | undefined>,
): Promise<T> {
  const response = await fetch(url(path, params))
  return handle<T>(response)
}

export async function apiPost<T>(path: string, json?: unknown): Promise<T> {
  const response = await fetch(url(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: json !== undefined ? JSON.stringify(json) : undefined,
  })
  return handle<T>(response)
}

export async function apiPatch<T>(path: string, json: unknown): Promise<T> {
  const response = await fetch(url(path), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(json),
  })
  return handle<T>(response)
}

export async function apiDelete<T>(
  path: string,
  params?: Record<string, string | boolean | undefined>,
  threadId?: number,
): Promise<T> {
  const qs: Record<string, string | boolean | undefined> = { ...params }
  if (threadId != null) qs.thread_id = String(threadId)
  const response = await fetch(url(path, Object.keys(qs).length ? qs : undefined), {
    method: 'DELETE',
  })
  return handle<T>(response)
}

export async function apiPostForm<T>(
  path: string,
  data: Record<string, string>,
  files?: File[],
): Promise<T> {
  const form = new FormData()
  for (const [k, v] of Object.entries(data)) form.append(k, v)
  for (const file of files ?? []) form.append('files', file)
  const response = await fetch(url(path), { method: 'POST', body: form })
  return handle<T>(response)
}

export async function apiPostFiles<T>(path: string, files: File[]): Promise<T> {
  const form = new FormData()
  for (const file of files) form.append('files', file)
  const response = await fetch(url(path), { method: 'POST', body: form })
  return handle<T>(response)
}

export async function* iterChatStream(
  message: string,
  files?: File[],
  threadId?: number,
): AsyncGenerator<StreamEvent> {
  const form = new FormData()
  form.append('message', message)
  if (threadId != null) form.append('thread_id', String(threadId))
  for (const file of files ?? []) form.append('files', file)

  const response = await fetch(url('/chat/stream'), { method: 'POST', body: form })
  if (response.status >= 400) {
    await handle(response)
    return
  }
  if (!response.body) throw new ApiError('Нет ответа от редакции.')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.trim()) continue
      try {
        yield JSON.parse(line) as StreamEvent
      } catch {
        /* обрезанный кусок стрима — ждём следующую строку */
      }
    }
  }
  if (buffer.trim()) {
    try {
      yield JSON.parse(buffer) as StreamEvent
    } catch {
      /* хвост без закрытой строки — игнорируем */
    }
  }
}

export function friendlyMessage(exc: unknown): string {
  if (exc instanceof ApiError) return exc.message
  if (exc instanceof TypeError && String(exc).includes('fetch')) {
    return 'Редакция сейчас молчит. Загляни чуть позже.'
  }
  return 'Что-то тихо не сложилось. Попробуй ещё раз.'
}
