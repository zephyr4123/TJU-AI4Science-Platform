// 两栏：对话为主，右边一张看板（需求 / 进度 / 结果 三个页签）；对话列表收在左侧抽屉。
// 页面只是 `ai4sci serve` 的客户端：所有数据经 `api/`，这里只管把它们摆在一起。

import { useCallback, useState } from 'react'

import { api } from '@/api/client'
import { ProgressBoard } from '@/boards/ProgressBoard'
import { RunBoard } from '@/boards/RunBoard'
import { TaskBoard } from '@/boards/TaskBoard'
import { ChatView } from '@/chat/ChatView'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'
import { ChatDrawer } from '@/sidebar/ChatDrawer'

type Board = 'task' | 'progress' | 'run'

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

  const healthy = health.loading && !health.data ? null : health.data?.ok === true

  return (
    <TooltipProvider>
      <div className="flex h-dvh overflow-hidden">
        <ChatView
          key={chatId ?? 'none'}
          chatId={chatId}
          boardOpen={boardOpen}
          onToggleBoard={() => setBoardOpen((v) => !v)}
          onNew={() => void newChat()}
          onTurnDone={turnDone}
          drawer={
            <ChatDrawer chats={chats.data} error={chats.error} selected={chatId} healthy={healthy}
                        creating={creating} onSelect={setPicked} onNew={() => void newChat()} />
          }
        />
        <aside
          className={cn('h-full shrink-0 border-l bg-sidebar transition-[width] duration-200',
                        boardOpen ? 'w-[30rem]' : 'w-0 overflow-hidden border-l-0')}
          aria-label="看板" aria-hidden={!boardOpen}
        >
          <Tabs value={board} onValueChange={(v) => setBoard(v as Board)} className="flex h-full w-[30rem] flex-col gap-0">
            <TabsList className="mx-6 mt-5 mb-2 grid w-auto grid-cols-3 bg-transparent p-0">
              <TabsTrigger value="task">需求</TabsTrigger>
              <TabsTrigger value="progress">进度</TabsTrigger>
              <TabsTrigger value="run">结果</TabsTrigger>
            </TabsList>
            <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
              <TabsContent value="task" className="mt-0">
                <TaskBoard epoch={epoch} selected={taskId} onSelect={setTaskId} />
              </TabsContent>
              <TabsContent value="progress" className="mt-0">
                <ProgressBoard epoch={epoch} onOpenTask={(id) => { setTaskId(id); setBoard('task') }}
                               onOpenRun={(id) => { setRunId(id); setBoard('run') }} />
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
