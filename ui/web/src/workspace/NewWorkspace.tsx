// 起一个工作区：一个工作区就是一份需求。没有工作区时它是主页面的欢迎屏；有了也能从顶栏再起一个。
import { useState } from 'react'

import { api } from '@/api/client'
import BlurText from '@/components/BlurText'
import { ErrorNote } from '@/components/bits'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import Waves from '@/components/Waves'

const ID_RE = /^[a-z][a-z0-9-]*$/

export function NewWorkspace({ first, onCreated, onCancel }: {
  first: boolean; onCreated: (id: string) => void; onCancel?: () => void
}) {
  const [id, setId] = useState('')
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const valid = ID_RE.test(id.trim())

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const made = await api.newWorkspace(id.trim(), title.trim())
      onCreated(made.id)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="relative h-full min-h-[32rem] flex-1">
      {/* Waves 自带一个跟随光标的小圆点，这里不需要，藏掉 */}
      <Waves lineColor="oklch(0.9 0.02 80)" backgroundColor="transparent" waveSpeedX={0.01} waveSpeedY={0.004}
             waveAmpX={28} waveAmpY={14} xGap={14} yGap={36} className="[&>div]:hidden" />
      <div className="relative mx-auto flex h-full max-w-[36rem] flex-col justify-center px-6">
        {first ? (
          <BlurText text="先起一个工作区。一个工作区，就是一份需求。" delay={50} animateBy="words"
                    direction="top" className="text-[2rem] leading-[1.25] font-semibold tracking-tight text-balance" />
        ) : (
          <h2 className="font-serif text-[1.75rem] leading-[1.25] font-semibold tracking-tight">再起一个工作区</h2>
        )}
        <p className="t-body mt-5 text-muted-foreground">
          这份需求的一切都住在里面：你和助理的对话、需求本身、取来的流、跑出来的每一次实验。课题组有几份需求就起几个。
        </p>
        <form className="mt-8 space-y-3" onSubmit={(e) => { e.preventDefault(); if (valid && !busy) void create() }}>
          <div>
            <Input value={id} aria-label="工作区名" placeholder="名字：小写英文加连字符，比如 rahman-stability"
                   className="bg-card font-mono" onChange={(e) => setId(e.target.value)} autoFocus />
            {id && !valid && <p className="mt-1 text-[0.8125rem] text-bad">只能用小写英文、数字、连字符，字母开头。</p>}
          </div>
          <Input value={title} aria-label="标题" placeholder="一句标题：给自己看的，比如「Rahman 模型多起点估计的稳定性」"
                 className="bg-card" onChange={(e) => setTitle(e.target.value)} />
          {error && <ErrorNote text={error} />}
          <div className="flex items-center gap-3 pt-2">
            <Button size="lg" type="submit" disabled={!valid || busy}>{busy ? '起着…' : '起这个工作区'}</Button>
            {onCancel && <Button variant="ghost" type="button" onClick={onCancel}>先不起</Button>}
          </div>
        </form>
      </div>
    </div>
  )
}
