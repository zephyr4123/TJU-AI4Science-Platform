// 起一个工作区：一句话就够（外层 #79 #80 #109，主人：别像表单）。玻璃输入框（和对话输入框同一只壳）里写要解决什么，回车即建；
// 文件夹名从标题里推（lib/slug），是内部 id，不给人看也不让人填；右边一张封面（reactbits TiltedCard 改装）随名字换——封面本来就是
// 按名字挑的（assets.coverOf），名字一变封面就换，让人看见这就是自己的工作区。输入框下面一行学科（库里 `templates/`，通用一份、
// 按学科几份）：选哪个学科，requirement.md 就照哪份模板起草，进主页面时助理接着问。底下铺循环视频（浅色云雾、深色光线汇聚）。字要少。
import { ArrowRight } from '@phosphor-icons/react'
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
import { suggestId } from '@/lib/slug'
import { useResource } from '@/lib/useResource'
import { useToken } from '@/lib/tokens'
import { cn } from '@/lib/utils'

/** 模板名给人看的学科：库里按学科加一份，这里加一个词；没写的照 name 显示 */
const TEMPLATE_WORD: Record<string, string> = { generic: '通用', ai: '人工智能', cs: '计算机', materials: '材料' }

export function NewWorkspace({ existing, onCreated, onCancel }: {
  existing: WorkspaceSummary[]
  onCreated: (id: string) => void
  onCancel?: () => void
}) {
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const templates = useResource(api.templates, [])
  const [template, setTemplate] = useState('generic')
  const indigo = useToken('--primary')
  const muted = useToken('--muted-foreground')
  const still = useReducedMotion()

  const id = suggestId(title, existing.map((w) => w.id), new Date())
  const ready = title.trim() !== '' && !busy

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const made = await api.newWorkspace(id, title.trim(), template)
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

          <div className="mt-3 flex min-h-7 max-w-[36rem] items-center gap-x-4 text-[0.8125rem] text-muted-foreground">
            {busy && (still ? <span>建目录</span> : <ShinyText text="建目录" color={muted} shineColor={indigo} speed={2} />)}
            {onCancel && (
              <button type="button" onClick={onCancel}
                      className="ml-auto underline decoration-border underline-offset-4 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
                取消
              </button>
            )}
          </div>
          {templates.data && templates.data.length > 0 && (
            <div className="mt-6 max-w-[36rem]">
              <div role="radiogroup" aria-label="学科" className="flex flex-wrap items-center gap-2">
                <span className="mr-1 text-[0.8125rem] text-muted-foreground">学科</span>
                {[...templates.data].sort((a, b) => Number(b.name === 'generic') - Number(a.name === 'generic')).map((t) => (
                  <button key={t.name} type="button" role="radio" aria-checked={template === t.name} title={t.summary}
                          onClick={() => setTemplate(t.name)}
                          className={cn('h-8 rounded-full border px-3 text-[0.8125rem] backdrop-blur-sm transition-colors focus-visible:outline-2 focus-visible:outline-ring',
                                        template === t.name ? 'border-primary bg-primary/10 text-primary' : 'bg-card/70 text-muted-foreground hover:border-primary/50 hover:text-foreground')}>
                    {TEMPLATE_WORD[t.name] ?? t.name}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-[0.75rem] text-muted-foreground/80">需求提纲按学科起草</p>
            </div>
          )}
          {error && <ErrorNote text={error} className="mt-3" />}
        </div>

        <div className="hidden lg:block">
          <TiltedCard cover={coverOf(id)} className="aspect-[8/5] w-full">
            <div className="px-5 pb-4">
              <p className={cn('font-serif text-[1.25rem] leading-snug font-semibold text-balance', !title.trim() && 'text-muted-foreground')}>
                {title.trim() || '你的课题'}
              </p>
              <p className="mt-1 text-[0.75rem] text-muted-foreground">{TEMPLATE_WORD[template] ?? template}</p>
            </div>
          </TiltedCard>
        </div>
      </div>
    </div>
  )
}
