// 起一个工作区：一个工作区就是一份需求，也就是一个文件夹——整个打包能交给同事（外层 #70 #74）。
// 这一屏没有表单：那句话本身就是要填的东西（记录本上的填空行），右边那只文件夹是全屏唯一放胆处，
// 名字一边打、标签一边显，打好了它就打开，露出里面会有的三样：需求、这条流、实验。
import { useState } from 'react'

import { api } from '@/api/client'
import type { WorkspaceSummary } from '@/api/types'
import { ErrorNote } from '@/components/bits'
import { Folder } from '@/components/reactbits/Folder'
import ShinyText from '@/components/reactbits/ShinyText'
import { Button } from '@/components/ui/button'
import { useToken } from '@/lib/tokens'
import { cn } from '@/lib/utils'

const ID_RE = /^[a-z][a-z0-9-]*$/

export function NewWorkspace({ existing, onCreated, onCancel, onPick }: {
  existing: WorkspaceSummary[]
  onCreated: (id: string) => void
  onCancel?: () => void
  onPick: (id: string) => void
}) {
  const [id, setId] = useState('')
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const indigo = useToken('--primary')
  const muted = useToken('--muted-foreground')
  const slug = id.trim()
  const valid = ID_RE.test(slug)
  const taken = existing.some((w) => w.id === slug)
  const first = existing.length === 0

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const made = await api.newWorkspace(slug, title.trim())
      onCreated(made.id)
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="paper-grid paper-grid-faint relative flex-1 overflow-y-auto">
      <form
        className="mx-auto grid min-h-full max-w-[72rem] gap-12 px-8 py-16 lg:grid-cols-[1fr_26rem] lg:items-center"
        onSubmit={(e) => { e.preventDefault(); if (valid && !taken && !busy) void create() }}
      >
        <div className="min-w-0">
          <h1 className="font-serif text-[2.25rem] leading-[1.2] font-semibold tracking-tight text-balance">
            {first ? '一个工作区，就是一份需求。' : '再起一份需求。'}
          </h1>
          <p className="t-body mt-4 max-w-[34rem] text-muted-foreground">
            它是一个文件夹：这份需求本身、为它取来的流、围绕它的对话、跑出来的每一次实验，都住在里面，整个能交给同事。
          </p>

          <p className="mt-12 font-serif text-[1.375rem] leading-[2.4] font-medium">
            <span>起一个工作区，叫</span>
            <Blank
              value={id} onChange={setId} mono autoFocus width="17ch" placeholder="rahman-stability"
              label="工作区名" invalid={id !== '' && (!valid || taken)}
            />
            <span>，</span>
            <br />
            <span>它要解决的是</span>
            <Blank value={title} onChange={setTitle} width="32ch" placeholder="Rahman 模型多起点估计的稳定性" label="标题" />
            <span>。</span>
          </p>
          <p className="mt-2 min-h-[1.5rem] text-[0.8125rem] text-muted-foreground">
            {id === '' ? '名字用小写英文、数字、连字符，它也是这份需求在盘上的目录名。'
              : taken ? '已经有一个叫这个的工作区了，换个名字。'
                : !valid ? '只能用小写英文、数字、连字符，字母开头。'
                  : <span className="font-mono">workspaces/{slug}/</span>}
          </p>
          {error && <ErrorNote text={error} className="mt-3" />}

          <div className="mt-8 flex items-center gap-4">
            <Button size="lg" type="submit" disabled={!valid || taken || busy}>{busy ? '起着…' : '起这个工作区'}</Button>
            {onCancel && <Button variant="ghost" type="button" onClick={onCancel}>先不起</Button>}
            {busy && <ShinyText text="正在建目录" color={muted} shineColor={indigo} speed={2} className="text-[0.8125rem]" />}
          </div>

          {!first && (
            <p className="mt-12 text-[0.875rem] text-muted-foreground">
              已有的：
              {existing.map((w, i) => (
                <span key={w.id}>
                  {i > 0 && '、'}
                  <button type="button" onClick={() => onPick(w.id)}
                          className="text-foreground underline decoration-border underline-offset-4 hover:decoration-primary focus-visible:outline-2 focus-visible:outline-ring">
                    {w.title}
                  </button>
                </span>
              ))}
            </p>
          )}
        </div>

        <div className="hidden justify-center overflow-visible pt-16 lg:flex">
          <Folder
            color={indigo} label={slug ? `workspaces/${slug}` : ''} open={valid && !taken} width={236}
            papers={[
              <Sheet key="task" title="需求" lines={['想解决什么', '数据在哪', '怎么算好']} />,
              <Sheet key="flow" title="这条流" lines={['从库里取一条', '按需要改参数', '照着跑']} />,
              <Sheet key="runs" title="实验" lines={['每一轮的账本', '分析', '验证与验收']} />,
            ]}
          />
        </div>
      </form>
    </div>
  )
}

/** 记录本上的一条填空线：没有框，只有底线；聚焦时底线变靛，填错变红。 */
function Blank({ value, onChange, placeholder, label, width, mono = false, invalid = false, autoFocus = false }: {
  value: string; onChange: (v: string) => void; placeholder: string; label: string; width: string
  mono?: boolean; invalid?: boolean; autoFocus?: boolean
}) {
  return (
    <input
      value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-label={label}
      autoFocus={autoFocus} spellCheck={false} autoComplete="off"
      style={{ width: `max(${width}, ${Math.max(value.length, 1) * (mono ? 1 : 2.2) + 3}ch)` }}
      className={cn('blank mx-2 max-w-full', mono ? 'font-mono text-[1.0625rem]' : 'font-serif',
                    invalid && 'blank-invalid')}
    />
  )
}

function Sheet({ title, lines }: { title: string; lines: string[] }) {
  return (
    <div className="space-y-1">
      <p className="font-serif text-[0.8125rem] font-semibold leading-tight">{title}</p>
      {lines.map((line) => <p key={line} className="text-[0.6875rem] leading-snug text-muted-foreground">{line}</p>)}
    </div>
  )
}
