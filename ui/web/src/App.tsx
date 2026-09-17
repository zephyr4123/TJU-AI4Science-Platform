// 壳：顶栏（名字、当前对话、花费、主页面 / 编辑台胶囊）+ 两块看板（外层 #58 #64）。
// 主页面改「实例」：对话为主，右边是流程脊柱——当前 run 照的那条流，没有 run 就是需求对齐（#67）；
// 编辑台改「库」：工作流墙、七段货架、拼流台，存成 workflows/<name>.yaml（#68）。页面只是 `ai4sci serve` 的客户端。
import { useCallback, useState } from 'react'

import { api } from '@/api/client'
import { ChatView } from '@/chat/ChatView'
import { PillNav } from '@/components/reactbits/PillNav'
import { TooltipProvider } from '@/components/ui/tooltip'
import { usd } from '@/lib/format'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'
import { ChatDrawer } from '@/sidebar/ChatDrawer'
import { Spine } from '@/spine/Spine'
import { Studio } from '@/studio/Studio'

type View = 'main' | 'studio'

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
  const [boardOpen, setBoardOpen] = useState(true)
  // 每完成一轮对话加一：助理可能运行了什么，看板据此重读
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
              className={cn('paper-grid relative h-full shrink-0 border-l transition-[width] duration-200',
                            boardOpen ? 'w-[27.5rem]' : 'w-0 overflow-hidden border-l-0')}
              aria-label="这条流" aria-hidden={!boardOpen}
            >
              <div className="h-full w-[27.5rem]"><Spine epoch={epoch} /></div>
            </aside>
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto"><Studio /></div>
        )}
      </div>
    </TooltipProvider>
  )
}
