// 一段对话的运行态：落盘的轮次、正在进行的这一轮、发送。还没有对话时第一句也从这里发——先开一段再发，
// 从按下回车起这一轮就已经在屏上，不是等对话建好再切过去（主人 2026-09-22：不要闪一下）。
// 项目页正中间的输入框、板里的对话视图（工作区页、编辑台）共用。
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { api, type Scope } from '@/api/client'
import { streamTurn } from '@/api/sse'
import type { Backend, ChatDoc, ChatEvent, ChatMeta, Tuning } from '@/api/types'
import { type Resource, useResource } from '@/lib/useResource'

import { outcome, reduceTrace } from './trace'
import { assembleTurns, type LiveTurn } from './turns'
import type { Turn } from './TurnView'
import { type TuningState, useTuning } from './useTuning'

export interface Conversation {
  doc: Resource<ChatDoc | null>
  turns: Turn[]
  /** 这一轮还在进行（含还没开出对话的那一会儿）：输入框不许再发 */
  busy: boolean
  /** 开不出来、发不出去的那一句；换到别的对话就不带过去 */
  error: string | null
  tuning: TuningState
  send: (text: string) => Promise<void>
}

export function useConversation({ scope, chatId, current, backends, create, onTurnDone }: {
  scope: Scope
  /** 看的哪段；null 是还没有对话，第一句会先开一段 */
  chatId: string | null
  current: ChatMeta | null
  backends: Backend[] | null
  /** 开一段（带上选的哪家与旋钮）；回来的那段由调用方随即当成 chatId */
  create: (tuning: Tuning, backend: string | null) => Promise<ChatMeta>
  /** 一轮结束：助理可能运行了命令、改了需求，看板要重读 */
  onTurnDone: () => void
}): Conversation {
  const doc = useResource(() => (chatId ? api.chat(scope, chatId) : Promise.resolve(null)), [chatId])
  // 第一句发出去的时候对话还没开，等发完要重读的是新开那段的：拿最新的 reload，不拿闭包里的
  const reload = useRef(doc.reload)
  useEffect(() => { reload.current = doc.reload }, [doc.reload])
  const [live, setLive] = useState<LiveTurn | null>(null)
  const [failure, setFailure] = useState<{ chatId: string | null; text: string } | null>(null)
  const t = useTuning(backends, current)
  const turns = useMemo(() => assembleTurns(doc.data?.history ?? [], live, chatId), [doc.data, live, chatId])
  const history = doc.data?.history ?? null

  const send = useCallback(async (text: string) => {
    setFailure(null)
    let turn: LiveTurn = { chatId, n: (history?.at(-1)?.turn ?? 0) + 1, message: text, trace: [], outcome: null }
    setLive(turn)
    let id = chatId
    if (!id) {
      try {
        id = (await create(t.tuning, t.backendName)).chat_id
      } catch (exc) {
        setLive(null)
        setFailure({ chatId: null, text: exc instanceof Error ? exc.message : String(exc) })
        return
      }
      turn = { ...turn, chatId: id }
      setLive(turn)
    }
    try {
      await streamTurn(scope, id, text, t.tuning, (event: ChatEvent) => {
        const done = event.kind === 'done' || event.kind === 'error' ? outcome(event) : turn.outcome
        turn = { ...turn, trace: reduceTrace(turn.trace, event), outcome: done }
        setLive(turn)
      })
    } catch (exc) {
      setFailure({ chatId: id, text: exc instanceof Error ? exc.message : String(exc) })
    }
    // 先重读落盘的轮次再撤掉屏上这一轮（assembleTurns 按轮次去重），人看不到闪
    await reload.current()
    setLive(null)
    onTurnDone()
  }, [chatId, create, history, onTurnDone, scope, t.backendName, t.tuning])

  return { doc, turns, busy: live !== null, error: failure && failure.chatId === chatId ? failure.text : null, tuning: t, send }
}
