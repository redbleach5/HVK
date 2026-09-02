import { useCallback, useEffect, useRef } from 'react'

import { useQuery, useQueryClient } from '@tanstack/react-query'

import { apiDelete, apiGet, friendlyMessage, iterChatStream } from '../api/client'

import type { ChatCard, ChatHistoryItem, ChatHistoryOut } from '../api/types'

import type { LocalMessage } from '../store/ui'

import { useChatStore, useUiStore } from '../store/ui'



function toLocal(msg: ChatHistoryItem): LocalMessage {

  return {

    id: msg.id,

    role: msg.role,

    content: msg.content,

    cards: (msg.cards ?? []) as ChatCard[],

    suggestion_ids: msg.suggestion_ids ?? [],

    created_at: msg.created_at,

  }

}



export function useChat(threadId?: number) {

  const queryClient = useQueryClient()

  const { showToast } = useUiStore()

  const {

    messages,

    isStreaming,

    prefill,

    setMessages,

    addMessage,

    updateLastAssistant,

    setStreaming,

    setPrefill,

    clearMessages,

  } = useChatStore()



  const historyKey =

    threadId != null ? (['chat', 'history', threadId] as const) : (['chat', 'history', 'latest'] as const)

  const prevKeyRef = useRef<string>('')



  const historyQuery = useQuery({

    queryKey: historyKey,

    queryFn: async () => {

      const data =

        threadId != null

          ? await apiGet<ChatHistoryOut>(`/chat/threads/${threadId}/history`)

          : await apiGet<ChatHistoryOut>('/chat/history')

      return {

        threadId: data.thread_id,

        messages: (data.messages ?? []).map(toLocal),

      }

    },

    refetchOnWindowFocus: false,

  })



  const activeThreadId = threadId ?? historyQuery.data?.threadId



  useEffect(() => {

    const key = historyKey.join(':')

    if (key !== prevKeyRef.current) {

      prevKeyRef.current = key

      if (!isStreaming) {

        clearMessages()

      }

    }

  }, [historyKey, isStreaming, clearMessages])



  useEffect(() => {

    if (isStreaming) return

    if (historyQuery.data?.messages) {

      setMessages(historyQuery.data.messages)

    }

  }, [historyQuery.data, isStreaming, setMessages])



  const sendMessage = useCallback(

    async (text: string, files?: File[]) => {

      const trimmed = text.trim()

      if (!trimmed && (!files || files.length === 0)) return



      const userContent = trimmed || '[фото]'

      addMessage({

        id: `u-${Date.now()}`,

        role: 'user',

        content: userContent,

        cards: [],

        suggestion_ids: [],

      })

      addMessage({

        id: `a-${Date.now()}`,

        role: 'assistant',

        content: '',

        cards: [],

        suggestion_ids: [],

        streaming: true,

        thinking: '',

      })

      setStreaming(true)

      setPrefill(null)



      let thinking = ''

      let reply = ''

      let cards: ChatCard[] = []

      let sids: number[] = []



      try {

        for await (const ev of iterChatStream(trimmed, files, activeThreadId)) {

          if (ev.t === 'thinking') {

            thinking += ev.d

            updateLastAssistant({ thinking })

          } else if (ev.t === 'search') {

            thinking += thinking ? `\nсмотрю: ${ev.q}` : `смотрю: ${ev.q}`

            updateLastAssistant({ thinking })

          } else if (ev.t === 'text') {

            reply += ev.d

            updateLastAssistant({ content: reply, thinking })

          } else if (ev.t === 'done') {

            reply = ev.reply || reply

            cards = ev.cards ?? []

            sids = ev.suggestion_ids ?? []

          }

        }

        const rest = cards.filter((c) => c.type !== 'thinking')
        const fromDone = cards.filter((c) => c.type === 'thinking')
        if (thinking) {
          rest.unshift({
            type: 'thinking',
            title: 'размышляю',
            body: thinking,
            data: {},
          })
        } else if (fromDone.length) {
          rest.unshift(...fromDone)
        }

        updateLastAssistant({

          content: reply,

          cards: rest,

          suggestion_ids: sids,

          streaming: false,

          thinking: undefined,

        })

        await queryClient.invalidateQueries({ queryKey: historyKey })

        await queryClient.invalidateQueries({ queryKey: ['chat', 'threads'] })

      } catch (exc) {

        const errText = friendlyMessage(exc)

        updateLastAssistant({

          content: errText,

          cards: [],

          suggestion_ids: [],

          streaming: false,

          thinking: undefined,

        })

        showToast(errText)

      } finally {

        setStreaming(false)

      }

    },

    [

      activeThreadId,

      addMessage,

      historyKey,

      queryClient,

      setPrefill,

      setStreaming,

      showToast,

      updateLastAssistant,

    ],

  )



  const clearHistory = useCallback(async () => {

    try {

      await apiDelete('/chat/history', { thread_id: String(activeThreadId) })

      clearMessages()

      await queryClient.invalidateQueries({ queryKey: historyKey })

      await queryClient.invalidateQueries({ queryKey: ['chat', 'threads'] })

      showToast('Диалог очищен')

    } catch (exc) {

      showToast(friendlyMessage(exc))

    }

  }, [activeThreadId, clearMessages, historyKey, queryClient, showToast])



  return {

    messages,

    isStreaming,

    prefill,

    setPrefill,

    sendMessage,

    clearHistory,

    historyLoading: historyQuery.isLoading,

    activeThreadId,

  }

}


