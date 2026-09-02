import { useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiDelete, apiGet, apiPost, friendlyMessage } from '../api/client'
import type { ChatThread, ChatThreadsOut } from '../api/types'
import { useUiStore } from '../store/ui'

export function useChatThreads() {
  const queryClient = useQueryClient()
  const { showToast } = useUiStore()

  const threadsQuery = useQuery({
    queryKey: ['chat', 'threads'],
    queryFn: () => apiGet<ChatThreadsOut>('/chat/threads'),
  })

  const invalidate = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ['chat', 'threads'] })
  }, [queryClient])

  const createMutation = useMutation({
    mutationFn: () => apiPost<ChatThread>('/chat/threads', {}),
    onSuccess: async () => {
      await invalidate()
    },
    onError: (exc) => showToast(friendlyMessage(exc)),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => apiDelete(`/chat/threads/${id}`),
    onSuccess: async () => {
      await invalidate()
      await queryClient.invalidateQueries({ queryKey: ['chat', 'history'] })
    },
    onError: (exc) => showToast(friendlyMessage(exc)),
  })

  const createThread = useCallback(async () => {
    return createMutation.mutateAsync()
  }, [createMutation])

  const deleteThread = useCallback(
    async (id: number) => {
      await deleteMutation.mutateAsync(id)
    },
    [deleteMutation],
  )

  return {
    threads: threadsQuery.data?.threads ?? [],
    threadsLoading: threadsQuery.isLoading,
    createThread,
    deleteThread,
    isCreating: createMutation.isPending,
    isDeleting: deleteMutation.isPending,
  }
}
