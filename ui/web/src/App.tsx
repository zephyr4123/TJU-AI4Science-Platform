// 三栏：左边对话列表，中间对话，右边三张看板（需求 / 编排 / 结果）。
// 页面只是 `ai4sci serve` 的客户端：所有数据经 `api/`，这里只管把它们摆在一起。

import { useCallback, useState } from 'react'

import { api } from '@/api/client'
import { FlowBoard } from '@/boards/FlowBoard'
import { RunBoard } from '@/boards/RunBoard'
import { TaskBoard } from '@/boards/TaskBoard'
import { ChatView } from '@/chat/ChatView'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'
import { Sidebar } from '@/sidebar/Sidebar'

type Board = 'task' | 'flow' | 'run'

export default function App() {
  const chats = useResource(api.chats, [])
  const health = useResource(api.health, [])
  const [picked, setPicked] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [board, setBoard] = useState<Board>('task')
  const [boardOpen, setBoardOpen] = useState(true)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  // 每完成一轮对话加一：助理可能按了按钮，看板据此重读
  const [epoch, setEpoch] = useState(0)

  // 没点过就落在最近的一段对话上（目录名带 UTC 时间戳，字典序最大的最新）
  const latest = chats.data?.length
    ? [...chats.data].sort((a, b) => b.chat_id.localeCompare(a.chat_id))[0].chat_id : null
  const chatId = picked ?? latest

  const newChat = useCallback(async () => {
    setCreating(true)
    try {
      const meta = await api.newChat()
      await chats.reload()
      setPicked(meta.chat_id)
    } finally {
      setCreating(false)
    }
  }, [chats])

  const turnDone = useCallback(() => {
    void chats.reload()
    setEpoch((e) => e + 1)
  }, [chats])

  return (
    <TooltipProvider>
      <div className="grid h-dvh grid-cols-[15rem_minmax(0,1fr)_auto] overflow-hidden">
        <Sidebar chats={chats.data} error={chats.error} selected={chatId}
                 healthy={health.loading && !health.data ? null : health.data?.ok === true}
                 creating={creating} onSelect={setPicked} onNew={() => void newChat()} />
        <ChatView key={chatId ?? 'none'} chatId={chatId} boardOpen={boardOpen}
                  onToggleBoard={() => setBoardOpen((v) => !v)}
                  onNew={() => void newChat()} onTurnDone={turnDone} />
        <aside className={cn('h-full min-h-0 border-l bg-muted/30 transition-[width] duration-200',
                             boardOpen ? 'w-[28rem]' : 'w-0 overflow-hidden border-l-0')}
               aria-label="看板" aria-hidden={!boardOpen}>
          <Tabs value={board} onValueChange={(v) => setBoard(v as Board)}
                className="flex h-full flex-col gap-0">
            <TabsList className="m-3 grid w-auto grid-cols-3">
              <TabsTrigger value="task">需求</TabsTrigger>
              <TabsTrigger value="flow">编排</TabsTrigger>
              <TabsTrigger value="run">结果</TabsTrigger>
            </TabsList>
            {/* 原生滚动而不是 ScrollArea：后者的视口让宽内容（账本表）把整栏撑开 */}
            <div className="min-h-0 w-[28rem] flex-1 overflow-x-hidden overflow-y-auto">
              <TabsContent value="task" className="mt-0">
                <TaskBoard epoch={epoch} selected={taskId} onSelect={setTaskId} />
              </TabsContent>
              <TabsContent value="flow" className="mt-0">
                <FlowBoard />
              </TabsContent>
              <TabsContent value="run" className="mt-0">
                <RunBoard epoch={epoch} selected={runId} onSelect={setRunId} />
              </TabsContent>
            </div>
          </Tabs>
        </aside>
      </div>
    </TooltipProvider>
  )
}
