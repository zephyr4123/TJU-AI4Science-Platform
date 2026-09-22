// 一个域里的对话清单与「当前这段」：项目（研究助理）与编辑台（流程助理）各用一份，逻辑相同。
// 开一段、删一段、每轮结束加一的 epoch 都在这儿；第一句怎么发在 chat/useConversation。
import { useCallback, useState } from 'react'

import { api, type Scope, scopeKey } from '@/api/client'
import type { ChatMeta, Tuning } from '@/api/types'

import { useResource } from './useResource'

export function useChats(scope: Scope) {
  const key = scopeKey(scope)
  const chats = useResource(() => api.chats(scope), [key])
  const [picked, setPicked] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  // 每完成一轮对话加一：助理可能运行了什么，看板据此重读
  const [epoch, setEpoch] = useState(0)

  // 没点过就落在最近的一段对话上（目录名带 UTC 时间戳，字典序最大的最新）
  const latest = chats.data?.length
    ? [...chats.data].sort((a, b) => b.chat_id.localeCompare(a.chat_id))[0].chat_id : null
  const chatId = picked ?? latest
  const current = chats.data?.find((c) => c.chat_id === chatId) ?? null

  // 开一段；`tuning` 与 `backend` 是门里选好的模型、思考深度与哪家，没选的服务从按人的设置抄（P-25）。开好就是当前这段
  const newChat = useCallback(async (tuning?: Tuning, backend?: string | null): Promise<ChatMeta> => {
    setCreating(true)
    try {
      const meta = await api.newChat(scope, tuning, backend ?? undefined)
      await chats.reload()
      setPicked(meta.chat_id)
      return meta
    } finally {
      setCreating(false)
    }
  }, [chats, scope])

  // 删一段：服务那边连这家 CLI 存的会话一起清；删的是当前这段就落回最近的一段。目录外没清的那几句原样交回去
  const remove = useCallback(async (chatId: string) => {
    const removed = await api.removeChat(scope, chatId)
    setPicked((now) => (now === chatId ? null : now))
    await chats.reload()
    return removed
  }, [chats, scope])

  const turnDone = useCallback(() => {
    void chats.reload()
    setEpoch((e) => e + 1)
  }, [chats])

  return { chats, chatId, current, creating, epoch, newChat, pick: setPicked, remove, turnDone }
}
