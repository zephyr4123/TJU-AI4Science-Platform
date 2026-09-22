// 起一个项目：一句话就够（外层 #79 #80 #109 #136，主人：别像表单）。玻璃输入框（和对话输入框同一只壳）里写要研究什么，
// 回车即建；底下一行「目标」可不填，写了进 project.md 标题下面那一段。文件夹名从标题里推（lib/slug），是内部 id，不给人看也不让人填。
// 第一个工作区不在这里起：进了项目跟助理说，它去开；或按项目页上的「新建工作区」。底下铺循环视频（浅色云雾、深色光线汇聚）。字要少。
import { ArrowRight } from '@phosphor-icons/react'
import { useReducedMotion } from 'motion/react'
import { type KeyboardEvent, type ReactNode, useState } from 'react'

import { api } from '@/api/client'
import type { ProjectSummary } from '@/api/types'
import { ASSETS } from '@/assets'
import { Backdrop } from '@/components/Backdrop'
import { ErrorNote } from '@/components/bits'
import GlassSurface from '@/components/reactbits/GlassSurface'
import ShinyText from '@/components/reactbits/ShinyText'
import { Button } from '@/components/ui/button'
import { suggestId } from '@/lib/slug'
import { useToken } from '@/lib/tokens'

export function NewProject({ existing, onCreated, onCancel, menu }: {
  existing: ProjectSummary[]
  onCreated: (id: string) => void
  onCancel?: () => void
  menu?: ReactNode
}) {
  const [title, setTitle] = useState('')
  const [goal, setGoal] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const indigo = useToken('--primary')
  const muted = useToken('--muted-foreground')
  const still = useReducedMotion()

  const id = suggestId(title, existing.map((p) => p.id), new Date(), 'project')
  const ready = title.trim() !== '' && !busy

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const made = await api.newProject(id, title.trim(), goal.trim())
      onCreated(made.id)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    // 中文输入法组词时的回车是选词，不是新建
    if (event.key === 'Enter' && !event.nativeEvent.isComposing) {
      event.preventDefault()
      if (ready) void create()
    }
  }

  return (
    <div className="relative flex-1 overflow-y-auto">
      <Backdrop clip={ASSETS.door} />
      {menu && <div className="absolute top-3 left-4 z-10">{menu}</div>}
      <div className="relative mx-auto flex min-h-full max-w-[44rem] flex-col justify-center px-6 py-16 sm:px-8">
        <h1 className="font-serif text-[2.25rem] leading-[1.2] font-semibold tracking-tight text-balance">要研究什么？</h1>

        <GlassSurface borderRadius={22} className="mt-10 focus-within:ring-3 focus-within:ring-ring/35">
          <div className="flex flex-col p-2">
            <div className="flex items-center gap-2">
              <input
                value={title} onChange={(event) => setTitle(event.target.value)} onKeyDown={onKeyDown}
                autoFocus spellCheck={false} autoComplete="off" aria-label="要研究什么"
                placeholder="Gradient–Update Alignment 在 PINN 上的复现"
                className="h-10 min-w-0 flex-1 bg-transparent px-2 text-[1rem] outline-none placeholder:text-muted-foreground/60"
              />
              <Button size="icon" className="rounded-full" onClick={() => void create()} disabled={!ready} aria-label="新建">
                <ArrowRight weight="bold" />
              </Button>
            </div>
            <div className="mx-2 h-px bg-border/70" />
            <input
              value={goal} onChange={(event) => setGoal(event.target.value)} onKeyDown={onKeyDown}
              spellCheck={false} autoComplete="off" aria-label="目标"
              placeholder="目标，可不填"
              className="h-9 min-w-0 bg-transparent px-2 text-[0.9375rem] text-muted-foreground outline-none placeholder:text-muted-foreground/60"
            />
          </div>
        </GlassSurface>

        <div className="mt-3 flex min-h-7 items-center gap-x-4 text-[0.8125rem] text-muted-foreground">
          {busy && (still ? <span>建目录</span> : <ShinyText text="建目录" color={muted} shineColor={indigo} speed={2} />)}
          {onCancel && (
            <button type="button" onClick={onCancel}
                    className="ml-auto underline decoration-border underline-offset-4 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
              取消
            </button>
          )}
        </div>
        {error && <ErrorNote text={error} className="mt-3" />}
      </div>
    </div>
  )
}
