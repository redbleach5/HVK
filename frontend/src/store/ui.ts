import { create } from 'zustand'
import type { ChatHistoryItem } from '../api/types'

interface UiState {
  toast: string | null
  showToast: (msg: string) => void
  clearToast: () => void
}

export const useUiStore = create<UiState>((set) => ({
  toast: null,
  showToast: (msg) => set({ toast: msg }),
  clearToast: () => set({ toast: null }),
}))

export interface LocalMessage extends Omit<ChatHistoryItem, 'id' | 'created_at'> {
  id: string | number
  created_at?: string
  streaming?: boolean
  thinking?: string
}

interface ChatState {
  messages: LocalMessage[]
  isStreaming: boolean
  prefill: string | null
  setMessages: (messages: LocalMessage[]) => void
  addMessage: (msg: LocalMessage) => void
  updateLastAssistant: (patch: Partial<LocalMessage>) => void
  setStreaming: (v: boolean) => void
  setPrefill: (text: string | null) => void
  clearMessages: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  isStreaming: false,
  prefill: null,
  setMessages: (messages) => set({ messages }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  updateLastAssistant: (patch) =>
    set((s) => {
      const messages = [...s.messages]
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].role === 'assistant') {
          messages[i] = { ...messages[i], ...patch }
          break
        }
      }
      return { messages }
    }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  setPrefill: (prefill) => set({ prefill }),
  clearMessages: () => set({ messages: [] }),
}))

interface DeskState {
  draftText: string
  planItemId: number | null
  setDraftText: (t: string) => void
  setPlanItemId: (id: number | null) => void
  draftFromNav: string | null
  setDraftFromNav: (t: string | null) => void
}

export const useDeskStore = create<DeskState>((set) => ({
  draftText: '',
  planItemId: null,
  setDraftText: (draftText) => set({ draftText }),
  setPlanItemId: (planItemId) => set({ planItemId }),
  draftFromNav: null,
  setDraftFromNav: (draftFromNav) => set({ draftFromNav }),
}))
