import { useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPatch } from '../api/client'
import type { DeskIn, DeskOut } from '../api/types'
import { useDeskStore } from '../store/ui'

export function useDesk() {
  const queryClient = useQueryClient()
  const { draftText, planItemId, setDraftText, setPlanItemId } = useDeskStore()

  const deskQuery = useQuery({
    queryKey: ['desk'],
    queryFn: () => apiGet<DeskOut>('/desk'),
  })

  const patchMutation = useMutation({
    mutationFn: (body: DeskIn) => apiPatch<DeskOut>('/desk', body),
    onSuccess: (data) => {
      queryClient.setQueryData(['desk'], data)
    },
  })

  const syncFromServer = useCallback(() => {
    const data = deskQuery.data
    if (!data) return
    if (draftText === '' && data.draft_text) setDraftText(data.draft_text)
    if (planItemId === null && data.plan_item_id != null) setPlanItemId(data.plan_item_id)
  }, [deskQuery.data, draftText, planItemId, setDraftText, setPlanItemId])

  const saveDesk = useCallback(
    async (patch?: DeskIn) => {
      await patchMutation.mutateAsync({
        draft_text: draftText,
        plan_item_id: planItemId,
        ...patch,
      })
    },
    [draftText, planItemId, patchMutation],
  )

  const rememberDraft = useCallback(
    async (text: string) => {
      setDraftText(text)
      await patchMutation.mutateAsync({ draft_text: text })
    },
    [patchMutation, setDraftText],
  )

  const rememberPlan = useCallback(
    async (id: number) => {
      setPlanItemId(id)
      await patchMutation.mutateAsync({ plan_item_id: id })
    },
    [patchMutation, setPlanItemId],
  )

  return {
    deskQuery,
    draftText,
    planItemId,
    setDraftText,
    setPlanItemId,
    saveDesk,
    rememberDraft,
    rememberPlan,
    syncFromServer,
  }
}
