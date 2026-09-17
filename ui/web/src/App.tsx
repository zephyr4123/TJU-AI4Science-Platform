// 壳：顶栏（名字、当前对话、花费、主页面 / 编辑台胶囊）+ 两块看板（外层 #58 #64）。
// 主页面改「实例」：对话为主，右边是当前 run 照的那条流（#67 换成脊柱，眼下先放需求 / 结果两页）；
// 编辑台改「库」：工作流墙、能力货架、拼流台（#68）。页面只是 `ai4sci serve` 的客户端。
import { useCallback, useState } from 'react'

import { api } from '@/api/client'
import { RunBoard } from '@/boards/RunBoard'
import { TaskBoard } from '@/boards/TaskBoard'
import { WorkflowBoard } from '@/boards/WorkflowBoard'
import { ChatView } from '@/chat/ChatView'
import { PillNav } from '@/components/reactbits/PillNav'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { TooltipProvider } from '@/components/ui/tooltip'
import { usd } from '@/lib/format'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'
import { ChatDrawer } from '@/sidebar/ChatDrawer'

type View = 'main' | 'studio'
type Board = 'task' | 'run'

const VIEWS: { id: View; label: string }[] = [
  { id: 'main', label: '主页面' },
  { id: 'studio', label: '编辑台' },
]

export default function App() {
  const chats = useResource(api.chats, [])
  const health = useResource(api.health, [])
  const [picked, setPicked] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [view, setView] = useState<View>('main')
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
  const current = chats.data?.find((c) => c.chat_id === chatId) ?? null

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
      <div className="flex h-dvh flex-col overflow-hidden">
        <header className="flex h-14 shrink-0 items-center gap-5 border-b bg-card px-5">
          <span className="font-serif text-[1.0625rem] font-semibold tracking-[0.02em]">AI4Science</span>
          <span className="min-w-0 flex-1 truncate text-[0.9375rem] text-muted-foreground">
            {current?.title ?? (chatId ? '还没开口的对话' : '还没有对话')}
          </span>
          {current && current.cost_usd > 0 && (
            <span className="t-label whitespace-nowrap">这段对话花了 {usd(current.cost_usd)}</span>
          )}
          <PillNav items={VIEWS} active={view} onSelect={setView} />
        </header>

        {view === 'main' ? (
          <div className="flex min-h-0 flex-1">
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
                <TabsList className="mx-6 mt-5 mb-2 grid w-auto grid-cols-2 bg-transparent p-0">
                  <TabsTrigger value="task">需求</TabsTrigger>
                  <TabsTrigger value="run">结果</TabsTrigger>
                </TabsList>
                <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
                  <TabsContent value="task" className="mt-0">
                    <TaskBoard epoch={epoch} selected={taskId} onSelect={setTaskId} />
                  </TabsContent>
                  <TabsContent value="run" className="mt-0">
                    <RunBoard epoch={epoch} selected={runId} onSelect={setRunId} />
                  </TabsContent>
                </div>
              </Tabs>
            </aside>
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto max-w-[64rem] px-8 py-8">
              <WorkflowBoard />
            </div>
          </div>
        )}
      </div>
    </TooltipProvider>
  )
}
