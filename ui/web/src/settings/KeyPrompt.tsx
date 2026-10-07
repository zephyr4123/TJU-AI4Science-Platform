// 「助理还不能说话」（外层 #282）：填一把 DeepSeek 的 key 就能好时页面弹的窗——粘贴 key、试通。问 key 从终端挪到这里，
// 桌面 App 第一次打开、一行命令装时回车跳过 key 的人都走它。只在后端说 needs_key 时弹（DeepSeek 缺 key、被拒，官方订阅
// 还没登录过）：试通会把助理与执行层都换成 DeepSeek，窗上照直说。什么时候弹、什么时候后台探一次是 `lib/keyPrompt` 的纯
// 函数；设置窗开着、那边有检查在跑时不弹，关了、跑完再看。「试通」走 `POST /settings/quickstart`：存 key、两家都切到
// DeepSeek、问一句，回来新的整份；通了关窗，没通把这次的原因写在窗里、窗留着（换一把 key 再试，或跳过）。
// 窗是产出窗同一种玻璃（components/GlassDialog），窄一些、没有关闭：「跳过」记在本机，Esc、点窗外只关这一次页面加载；
// 试通途中关不掉。自己弹出来时焦点不进框（人可能正在别处打字，回车会把那半句当 key 发出去）；设置里点「填 key」打开的才进。
import { useEffect, useRef, useState } from 'react'

import { api } from '@/api/client'
import type { AssistantStatus, SettingsDoc } from '@/api/types'
import { ErrorNote } from '@/components/bits'
import { GlassDialog, GlassTitle } from '@/components/GlassDialog'
import CallChip, { type CallChipStatus } from '@/components/reactbits/CallChip'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { forgetSkip, keyPromptStep, rememberSkip, skipMark, storedSkip } from '@/lib/keyPrompt'

import { CHECK_MS } from './kit'

/** DeepSeek 开放平台上申请 key 的那一页 */
const APPLY = 'https://platform.deepseek.com/api_keys'

/** 一次页面加载只后台探一次：记在模块里，StrictMode 下 effect 跑两遍、设置窗关了又开都不重探 */
let probedThisLoad = false

export function KeyPrompt({ assistant, paused, probe, onDoc, asked }: {
  /** `/settings` 的 `assistant`；设置还没取到是 null */
  assistant: AssistantStatus | null
  /** 设置窗开着、或那边有检查在跑：先不弹 */
  paused: boolean
  /** 后台探一次助理那家（`POST /settings/check`，走设置窗那条路，那家的「检查」片跟着动） */
  probe: (agent: string) => void
  /** 试通回来的整份：设置窗与外面跟着换 */
  onDoc: (doc: SettingsDoc) => void
  /** 设置里点了几次「填 key」：变了就把跳过、关过都作废，弹出来、焦点进框 */
  asked: number
}) {
  const [skipped, setSkipped] = useState<string | null>(storedSkip)
  // 这次页面加载里点窗外、按 Esc 关掉的那一次（不记在本机）
  const [dismissed, setDismissed] = useState<string | null>(null)
  // 试过、没通：不管这次回来的是缺 key 还是说不了话，窗都留着，原因写在窗里
  const [tried, setTried] = useState(false)
  const [key, setKey] = useState('')
  const [chip, setChip] = useState<CallChipStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const busy = chip === 'running'
  // 试通途中框是禁用的，焦点掉到页面上；没通时放回框里，好直接粘下一把
  const field = useRef<HTMLInputElement>(null)
  useEffect(() => { if (chip === 'error') field.current?.focus() }, [chip])

  useEffect(() => {
    if (!asked) return
    forgetSkip()
    setSkipped(null)
    setDismissed(null)
  }, [asked])

  const step = keyPromptStep(assistant, [skipped, dismissed], probedThisLoad)
  useEffect(() => {
    if (step !== 'probe' || !assistant || probedThisLoad) return
    probedThisLoad = true
    probe(assistant.agent)
  }, [step, assistant, probe])

  const close = (remember: boolean) => {
    const mark = assistant ? skipMark(assistant) : ''
    if (remember) {
      setSkipped(mark)
      rememberSkip(mark)
    } else {
      setDismissed(mark)
    }
    setTried(false)
    setError(null)
    setChip('idle')
  }
  const ready = key.trim() !== '' && !busy
  const tryKey = async () => {
    setChip('running')
    setError(null)
    try {
      const next = await api.quickstart(key.trim())
      onDoc(next)
      if (next.assistant.state === 'ready') {
        setTried(false)
        setKey('')
        setChip('idle')
      } else {
        setTried(true)
        setError(next.assistant.reason ?? '未通过')
        setChip('error')
      }
    } catch (exc) {
      setTried(true)
      setError(exc instanceof Error ? exc.message : String(exc))
      setChip('error')
    }
  }

  return (
    <GlassDialog open={!paused && (tried || step === 'ask')} onOpenChange={(open) => { if (!open && !busy) close(false) }}
                 showCloseButton={false} className="w-[min(28rem,calc(100vw-2rem))]" describedBy="key-prompt-note"
                 onOpenAutoFocus={(e) => { if (!asked) { e.preventDefault(); (e.currentTarget as HTMLElement).focus() } }}>
      <form className="flex flex-col gap-4 p-6" onSubmit={(e) => { e.preventDefault(); if (ready) void tryKey() }}>
        <header className="flex flex-col gap-1">
          <GlassTitle>助理还不能说话</GlassTitle>
          <p id="key-prompt-note" className="t-label">填一把 DeepSeek 的 key 就能用，助理与执行层都会换成 DeepSeek</p>
        </header>
        <Input ref={field} type="password" value={key} onChange={(e) => setKey(e.target.value)} disabled={busy} spellCheck={false} autoComplete="off"
               aria-label="DeepSeek 的 key" placeholder="粘贴 DeepSeek 的 key" className="h-9 bg-card" />
        {error && <ErrorNote text={error} />}
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-3">
          <a href={APPLY} target="_blank" rel="noreferrer" className="mr-auto text-[0.8125rem] text-primary underline-offset-3 hover:underline">
            platform.deepseek.com 申请
          </a>
          <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={() => close(true)}>跳过</Button>
          <CallChip label="试通" status={chip} expectedMs={CHECK_MS} disabled={!ready} onPress={() => void tryKey()} />
        </div>
      </form>
    </GlassDialog>
  )
}
