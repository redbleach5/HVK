export type ChatCardType =
  | 'thinking'
  | 'why'
  | 'idea'
  | 'edit'
  | 'photo'
  | 'photo_advice'
  | 'concierge'
  | 'inbox'
  | 'archive'
  | 'analytics'
  | 'plan_item'
  | 'publish'
  | 'web'

export interface ChatCard {
  type: ChatCardType | string
  title: string
  body: string
  data: Record<string, unknown>
  suggestion_id?: number | null
}

export interface ChatHistoryItem {
  id: number
  role: 'user' | 'assistant'
  content: string
  cards: ChatCard[]
  suggestion_ids: number[]
  created_at: string
}

export interface ChatThread {
  id: number
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface ChatThreadsOut {
  threads: ChatThread[]
}

export interface ChatHistoryOut {
  thread_id: number
  messages: ChatHistoryItem[]
}

export interface ChatOut {
  reply: string
  cards: ChatCard[]
  suggestion_ids: number[]
  intent: string
}

export type StreamEvent =
  | { t: 'open' }
  | { t: 'thinking'; d: string }
  | { t: 'text'; d: string }
  | { t: 'search'; q: string }
  | {
      t: 'done'
      reply: string
      cards: ChatCard[]
      suggestion_ids: number[]
      intent?: string
    }

export interface OnboardingStatus {
  step: number
  done: boolean
  blog_name: string
  about: string
  posts_imported: number
  voice_ready: boolean
}

export interface DeskOut {
  desk: string
  draft_text: string
  plan_item_id: number | null
}

export interface DeskIn {
  desk?: string
  draft_text?: string
  plan_item_id?: number | null
}

export interface HealthStatus {
  ok: boolean
  brain: boolean
  eyes: boolean
  vk_configured: boolean
  telegram_configured: boolean
  message: string
}

export interface DiagnosticsOut {
  ok: boolean
  checked_at: string
  author_hint?: string | null
  issues: string[]
  checks: Record<string, unknown>[]
  chat_latency: Record<string, unknown>
  json_latency: Record<string, unknown>
  recent_calls: Record<string, unknown>[]
  ops_insight?: string | null
}

export interface WhyBlock {
  summary: string
  related_posts?: string[]
  seasonality?: string | null
  audience_pattern?: string | null
}

export interface IdeaCard {
  id?: number
  theme: string
  description?: string
  format?: string
  effort?: string
  why_now?: string
  personal_angle?: string
  visual?: string
  why?: WhyBlock
  suggestion_id?: number
}

export interface TodayResponse {
  digest: string
  highlights: { text?: string }[]
  ideas: IdeaCard[]
  plan_reminders: string[]
  activity: { created_at?: string; summary?: string }[]
  why?: WhyBlock
}

export interface PlanItemOut {
  id: number
  idea_id?: number | null
  title: string
  draft_text: string
  status: 'conceived' | 'written' | 'published'
  scheduled_date?: string | null
  published_post_id?: number | null
}

export interface PhotoAnalysis {
  verdict: string
  scores: Record<string, number>
  advice: string[]
  caption_direction: string
  why?: WhyBlock
  best_in_series?: number | null
  series_comparison?: string | null
  suggestion_id?: number
  advice_suggestions?: { text: string; suggestion_id?: number }[]
}

export interface TextEdit {
  original: string
  revised: string
  explanation: string
  suggestion_id?: number
}

export interface EditorResult {
  revised_text: string
  edits: TextEdit[]
  alternative_openings: string[]
  in_voice: boolean
  voice_notes: string
  why?: WhyBlock
  suggestion_id?: number
}

export interface AnalyticsOut {
  series: { date: string; engagement: number }[]
  top_posts: { theme?: string; engagement?: number; text?: string }[]
  report?: AudienceReport | null
  posts_count: number
}

export interface AudienceReport {
  portrait?: string
  what_works?: string[]
  frequent_questions?: string[]
  unmet_needs?: string[]
  recommendations?: string[]
  insights?: { title?: string; body?: string; based_on?: string; why?: WhyBlock }[]
  why?: WhyBlock
  suggestion_id?: number
}

export interface ArchiveHit {
  post_id?: number
  theme?: string
  text_preview?: string
  engagement?: number
  why_relevant?: string
}

export interface ArchiveSearchResult {
  hits: ArchiveHit[]
  why?: WhyBlock
}

export interface InboxItem {
  peer_id: number
  preview: string
  date?: string
  unread: number
}

export interface InboxOut {
  items: InboxItem[]
  available: boolean
  message: string
}

export interface ConciergeReply {
  category: string
  category_label?: string
  draft_reply: string
  related_post?: string
  suggestion_id?: number
}

export interface VoiceProfileOut {
  version: number
  profile: Record<string, unknown>
  created_at: string
}

export interface PublishOut {
  ok: boolean
  vk_post_id?: string
  photos_attached?: number
  photos_warning?: string | null
}

export type DeskPage =
  | 'today'
  | 'photo'
  | 'text'
  | 'ideas'
  | 'analytics'
  | 'concierge'

export const DESK_LABELS: Record<DeskPage, string> = {
  today: 'Сегодня',
  photo: 'Фото',
  text: 'Текст',
  ideas: 'Идеи и план',
  analytics: 'Аналитика',
  concierge: 'ЛС',
}
