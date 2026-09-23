// 编辑台（外层 #100 #112）：全局一个流程库，两个镜头——流程（画布）与能力（陈列与详情），页眉上切换；流程助理的对话在右边
// 那块板上（与工作区页同一块 ChatPanel，但这边是浮窗：画布铺到底、板浮在右边，主人 2026-09-23）。和项目的世界平行：不跟着项目换。
import { type ReactNode, useState } from 'react'

import { STUDIO } from '@/api/client'
import type { Backend } from '@/api/types'
import { ASSETS } from '@/assets'
import { ChatDrawer } from '@/chat/ChatDrawer'
import { ChatPanel } from '@/chat/ChatPanel'
import { ChatView } from '@/chat/ChatView'
import { WELCOME } from '@/chat/Welcome'
import { Top } from '@/components/Top'
import { useChats } from '@/lib/useChats'

import { Studio, type StudioView } from './Studio'

export function StudioPlace({ healthy, backends, menu }: { healthy: boolean | null; backends: Backend[] | null; menu?: ReactNode }) {
  const c = useChats(STUDIO)
  // 镜头与「能力」镜头里打开的详情：从画布 / 配置板点一个能力的名字过来时两样一起设
  const [view, setView] = useState<StudioView>('flow')
  const [focus, setFocus] = useState<string | null>(null)
  return (
    <>
      <Top menu={menu} title="编辑台" picture={ASSETS.studio}
           lens={{ value: view, options: [{ value: 'flow', label: '流程' }, { value: 'caps', label: '能力' }],
                   onChange: (v) => { setView(v as StudioView); setFocus(null) } }} />
      <div className="relative flex min-h-0 flex-1">
        <ChatPanel float chat={(close) => (
          <ChatView
            scope={STUDIO} chatId={c.chatId} current={c.current} onClose={close} create={c.newChat}
            onTurnDone={c.turnDone}
            backends={backends}
            welcome={WELCOME.studio}
            drawer={
              <ChatDrawer chats={c.chats.data} error={c.chats.error} selected={c.chatId} healthy={healthy}
                          creating={c.creating} onSelect={c.pick} onNew={() => void c.newChat()}
                          onRemove={async (id) => { await c.remove(id) }}
                          cover={ASSETS.studio} title="编辑台" />
            }
          />
        )}>
          <Studio epoch={c.epoch} view={view} focus={focus} onFocus={(name) => { setFocus(name); if (name) setView('caps') }} />
        </ChatPanel>
      </div>
    </>
  )
}
