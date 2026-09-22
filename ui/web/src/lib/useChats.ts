// 一个域里的对话清单与「当前这段」：主页面（工作区）与编辑台（造流）各用一份，逻辑相同。
import { useCallback, useState } from 'react'

import { api, type Scope } from '@/api/client'
import type { Tuning } from '@/api/types'

import { useResource } from './useResource'

export function useChats(scope: Scope) {
  const key = scope.kind === 'studio' ? 'studio' : scope.id
  const chats = useResource(() => api.chats(scope), [key])
  const [picked, setPicked] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  // 输入框就是门：还没有对话时打的第一句话，先开一段，再由新对话的视图发出去
  const [opening, setOpening] = useState<string | null>(null)
  // 每完成一轮对话加一：助理可能运行了什么，看板据此重读
  const [epoch, setEpoch] = useState(0)

  // 没点过就落在最近的一段对话上（目录名带 UTC 时间戳，字典序最大的最新）
  const latest = chats.data?.length
    ? [...chats.data].sort((a, b) => b.chat_id.localeCompare(a.chat_id))[0].chat_id : null
  const chatId = picked ?? latest
  const current = chats.data?.find((c) => c.chat_id === chatId) ?? null

  // 开一段；`tuning` 与 `backend` 是门里选好的模型、思考深度与哪家，没选的服务从按人的设置抄（P-25）
  const newChat = useCallback(async (tuning?: Tuning, backend?: string | null) => {
    setCreating(true)
    try {
      const meta = await api.newChat(scope, tuning, backend ?? undefined)
      await chats.reload()
      setPicked(meta.chat_id)
    } finally {
      setCreating(false)
    }
  }, [chats, scope])

  const start = useCallback(async (text: string, tuning: Tuning, backend: string | null) => {
    setOpening(text)
    await newChat(tuning, backend)
  }, [newChat])

  const opened = useCallback(() => setOpening(null), [])

  const turnDone = useCallback(() => {
    void chats.reload()
    setEpoch((e) => e + 1)
  }, [chats])

  return { chats, chatId, current, creating, epoch, newChat, opening, start, opened, pick: setPicked, turnDone }
}
