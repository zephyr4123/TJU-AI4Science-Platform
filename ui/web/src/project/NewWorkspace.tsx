// 在项目里起一个工作区：项目页「工作区」那一行按了「新建」才在清单顶上展开这一块（与设置页「添加」同一条规矩：表单不常驻，
// 加完收回去）。一句话说清课题、选个学科（库里 `templates/`，通用一份、按学科几份；requirement.md 照哪份模板起草）、回车即建；
// 文件夹名从标题里推（lib/slug），是内部 id，不给人看也不让人填。建好直接进那个工作区，跟助理把需求填起来。
import { ArrowRight } from '@phosphor-icons/react'
import { useReducedMotion } from 'motion/react'
import { type KeyboardEvent, useState } from 'react'

import { api } from '@/api/client'
import { ErrorNote } from '@/components/bits'
import GlassSurface from '@/components/reactbits/GlassSurface'
import ShinyText from '@/components/reactbits/ShinyText'
import { Button } from '@/components/ui/button'
import { suggestId } from '@/lib/slug'
import { useResource } from '@/lib/useResource'
import { useToken } from '@/lib/tokens'
import { cn } from '@/lib/utils'

/** 模板名给人看的学科：库里按学科加一份，这里加一个词；没写的照 name 显示 */
const TEMPLATE_WORD: Record<string, string> = { generic: '通用', ai: '人工智能', cs: '计算机', materials: '材料', reproduce: '论文复现' }

export function NewWorkspace({ project, existing, onCreated, onCancel }: {
  project: string
  /** 项目里已有的工作区 id：新名字不能撞 */
  existing: string[]
  onCreated: (id: string) => void
  onCancel: () => void
}) {
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const templates = useResource(api.templates, [])
  const [template, setTemplate] = useState('generic')
  const indigo = useToken('--primary')
  const muted = useToken('--muted-foreground')
  const still = useReducedMotion()

  const id = suggestId(title, existing, new Date())
  const ready = title.trim() !== '' && !busy

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const made = await api.newWorkspace(project, id, title.trim(), template)
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
    if (event.key === 'Escape') onCancel()
  }

  return (
    <div className="space-y-3">
      <GlassSurface borderRadius={18} className="focus-within:ring-3 focus-within:ring-ring/35">
        <div className="flex items-center gap-2 p-1.5">
          <input
            value={title} onChange={(event) => setTitle(event.target.value)} onKeyDown={onKeyDown}
            autoFocus spellCheck={false} autoComplete="off" aria-label="这个工作区做什么"
            placeholder="相关工作综述"
            className="h-9 min-w-0 flex-1 bg-transparent px-2 text-[0.9375rem] outline-none placeholder:text-muted-foreground/60"
          />
          <Button size="icon-sm" className="rounded-full" onClick={() => void create()} disabled={!ready} aria-label="新建">
            <ArrowRight weight="bold" />
          </Button>
        </div>
      </GlassSurface>
      <div className="flex min-h-7 flex-wrap items-center gap-x-4 gap-y-2 text-[0.8125rem] text-muted-foreground">
        {templates.data && templates.data.length > 0 && (
          <div role="radiogroup" aria-label="学科" className="flex flex-wrap items-center gap-2">
            <span className="mr-1">学科</span>
            {[...templates.data].sort((a, b) => Number(b.name === 'generic') - Number(a.name === 'generic')).map((t) => (
              <button key={t.name} type="button" role="radio" aria-checked={template === t.name} title={t.summary}
                      onClick={() => setTemplate(t.name)}
                      className={cn('h-7 rounded-full border px-2.5 text-[0.8125rem] backdrop-blur-sm transition-colors focus-visible:outline-2 focus-visible:outline-ring',
                                    template === t.name ? 'border-primary bg-primary/10 text-primary' : 'bg-card/70 text-muted-foreground hover:border-primary/50 hover:text-foreground')}>
                {TEMPLATE_WORD[t.name] ?? t.name}
              </button>
            ))}
          </div>
        )}
        {busy && (still ? <span>建目录</span> : <ShinyText text="建目录" color={muted} shineColor={indigo} speed={2} />)}
        <button type="button" onClick={onCancel}
                className="ml-auto underline decoration-border underline-offset-4 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
          取消
        </button>
      </div>
      {error && <ErrorNote text={error} />}
    </div>
  )
}
