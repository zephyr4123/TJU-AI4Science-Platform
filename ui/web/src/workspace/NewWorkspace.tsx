// 起一个工作区：一句话就够（外层 #79 #80，主人：别像表单）。玻璃输入框（和对话输入框同一只壳）里写要解决什么，回车即建；
// 文件夹名从标题里推（lib/slug），小字里可以改；右边一张封面（reactbits TiltedCard 改装）随名字换——封面本来就是按名字挑的
// （assets.coverOf），名字一变封面就换，让人看见这就是自己的工作区。底下铺循环视频（浅色云雾、深色光线汇聚）。字要少。
import { ArrowRight, PencilSimple } from '@phosphor-icons/react'
import { useReducedMotion } from 'motion/react'
import { type KeyboardEvent, useState } from 'react'

import { api } from '@/api/client'
import type { WorkspaceSummary } from '@/api/types'
import { ASSETS, coverOf } from '@/assets'
import { Backdrop } from '@/components/Backdrop'
import { ErrorNote } from '@/components/bits'
import GlassSurface from '@/components/reactbits/GlassSurface'
import ShinyText from '@/components/reactbits/ShinyText'
import { TiltedCard } from '@/components/reactbits/TiltedCard'
import { Button } from '@/components/ui/button'
import { ID_RE, suggestId } from '@/lib/slug'
import { useToken } from '@/lib/tokens'
import { cn } from '@/lib/utils'

export function NewWorkspace({ existing, onCreated, onCancel }: {
  existing: WorkspaceSummary[]
  onCreated: (id: string) => void
  onCancel?: () => void
}) {
  const [title, setTitle] = useState('')
  // 研究者自己改过的文件夹名；清空就回到按标题推
  const [named, setNamed] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const indigo = useToken('--primary')
  const muted = useToken('--muted-foreground')
  const still = useReducedMotion()

  const taken = existing.map((w) => w.id)
  const id = named.trim() || suggestId(title, taken, new Date())
  const wellFormed = ID_RE.test(id)
  const dup = taken.includes(id)
  const ready = title.trim() !== '' && wellFormed && !dup && !busy

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const made = await api.newWorkspace(id, title.trim())
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
      <div className="relative mx-auto grid min-h-full max-w-[72rem] items-center gap-12 px-6 py-16 sm:px-8 lg:grid-cols-[1fr_22rem]">
        <div className="min-w-0">
          <h1 className="font-serif text-[2.25rem] leading-[1.2] font-semibold tracking-tight text-balance">要解决什么？</h1>

          <GlassSurface borderRadius={22} className="mt-10 max-w-[36rem] focus-within:ring-3 focus-within:ring-ring/35">
            <div className="flex items-center gap-2 p-2">
              <input
                value={title} onChange={(event) => setTitle(event.target.value)} onKeyDown={onKeyDown}
                autoFocus spellCheck={false} autoComplete="off" aria-label="要解决什么"
                placeholder="Rahman 模型多起点估计的稳定性"
                className="h-9 min-w-0 flex-1 bg-transparent px-2 text-[1rem] outline-none placeholder:text-muted-foreground/60"
              />
              <Button size="icon" className="rounded-full" onClick={() => void create()} disabled={!ready} aria-label="新建">
                <ArrowRight weight="bold" />
              </Button>
            </div>
          </GlassSurface>

          <div className="mt-3 flex min-h-7 max-w-[36rem] flex-wrap items-center gap-x-4 gap-y-1 text-[0.8125rem] text-muted-foreground">
            <label className={cn('flex h-7 items-center gap-1.5 rounded-full border bg-card/70 pr-2.5 pl-2 backdrop-blur-sm transition-colors focus-within:border-primary',
                                 (!wellFormed || dup) && 'border-bad text-bad')}>
              <PencilSimple className="size-3.5" />
              <input
                value={id} onChange={(event) => setNamed(event.target.value)} spellCheck={false} autoComplete="off" aria-label="文件夹名"
                style={{ width: `${Math.max(id.length, 4) + 1}ch` }}
                className="bg-transparent font-mono text-[0.8125rem] text-foreground outline-none"
              />
            </label>
            {!wellFormed ? <span className="text-bad">只能小写英文、数字、连字符，字母开头</span>
              : dup ? <span className="text-bad">重名了</span>
                : busy ? (still ? <span>建目录</span> : <ShinyText text="建目录" color={muted} shineColor={indigo} speed={2} />)
                  : null}
            {onCancel && (
              <button type="button" onClick={onCancel}
                      className="ml-auto underline decoration-border underline-offset-4 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
                取消
              </button>
            )}
          </div>
          {error && <ErrorNote text={error} className="mt-3" />}
        </div>

        <div className="hidden lg:block">
          <TiltedCard cover={coverOf(id)} className="aspect-[8/5] w-full">
            <div className="px-5 pb-4">
              <p className={cn('font-serif text-[1.25rem] leading-snug font-semibold text-balance', !title.trim() && 'text-muted-foreground')}>
                {title.trim() || '你的课题'}
              </p>
              <p className="mt-1 font-mono text-[0.75rem] text-muted-foreground">{id}</p>
            </div>
          </TiltedCard>
        </div>
      </div>
    </div>
  )
}
