// 设置窗里各页共用的件（外层 #268）：一节（小标题 + 一行一项，行间一道淡线）、一项（左边名字与一句淡字，右边控件）、
// 状态一行（脉冲点 + 词 + 几项数）、粘贴 key 的那一格。照 Claude 应用的设置：后面加设置就是往某页加一节、一行。
import { type ReactNode, useState } from 'react'

import { api } from '@/api/client'
import type { SettingsDoc } from '@/api/types'
import type { CallChipStatus } from '@/components/reactbits/CallChip'
import HoldButton from '@/components/reactbits/HoldButton'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

import type { Status, Tone } from './status'

/** 一个动作：忙着时整窗的键都歇着，回来的整份替换掉；`judge` 看回来的那份这次算不算过 */
export interface Ctx {
  busy: string | null
  chip: (key: string) => CallChipStatus
  act: (key: string, run: () => Promise<SettingsDoc>, judge?: (doc: SettingsDoc) => boolean) => Promise<void>
}

/** 检查大概要跑多久（片上的底色填到九成用这么久）：一家底座 pong 一次几秒，全部一起十几秒 */
export const CHECK_MS = 9000

/** 一节：宋体小标题（旁边可带一句淡字、右边可带动作），底下一行一项 */
export function Section({ title, note, action, children }: {
  title: string; note?: string; action?: ReactNode; children: ReactNode
}) {
  return (
    <section aria-label={title} className="not-first:mt-9">
      <header className="flex min-h-8 flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="font-serif text-[1.0625rem] font-semibold">{title}</h3>
        {note && <span className="text-[0.75rem] text-muted-foreground">{note}</span>}
        {action && <span className="ml-auto">{action}</span>}
      </header>
      <div className="mt-1 divide-y divide-foreground/[0.07]">{children}</div>
    </section>
  )
}

/** 一项：左边名字、底下一句淡字；右边控件，窄了掉到下一行靠右 */
export function Row({ label, note, children }: { label: ReactNode; note?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2.5 py-3.5">
      <div className="min-w-[9rem] flex-1">
        <div className="text-[0.875rem] font-medium">{label}</div>
        {note && <div className="mt-1 text-[0.8125rem] leading-snug text-muted-foreground">{note}</div>}
      </div>
      {children && <div className="ml-auto flex max-w-full shrink-0 items-center gap-1.5">{children}</div>}
    </div>
  )
}

/** 一项的值（不能改的那种）：路径、个数、大小 */
export function Value({ children, title, className }: { children: ReactNode; title?: string; className?: string }) {
  return <span title={title} className={cn('min-w-0 truncate text-[0.875rem] tabular', className)}>{children}</span>
}

const WORD_CLASS: Record<Tone, string> = { ok: 'text-ok', bad: 'text-bad', neutral: 'text-muted-foreground' }

/** 脉冲点：过了是铜绿点外一圈慢慢扩开的心跳；没过是静止的红点；没检查是空心圈。字在旁边，点本身不读出来 */
export function Pulse({ tone }: { tone: Tone }) {
  return (
    <span aria-hidden="true" className="relative inline-flex size-2.5 shrink-0 translate-y-px items-center justify-center self-center">
      {tone === 'ok' && <span className="absolute inset-0 rounded-full bg-ok/45 animate-pulse-ring motion-reduce:hidden" />}
      <span className={cn('relative size-2 rounded-full',
                          tone === 'ok' && 'bg-ok', tone === 'bad' && 'bg-bad',
                          tone === 'neutral' && 'ring-1 ring-inset ring-muted-foreground/70')} />
    </span>
  )
}

/** 一处状态：点 + 词 + 几项数一行，后面可以跟一段淡字（地址）；没过时机器的原话另起一行，长了截断、悬停看全 */
export function StatusLine({ status, tail }: { status: Status; tail?: string }) {
  return (
    <span className="block min-w-0 space-y-1">
      <span className="flex min-w-0 items-baseline gap-2">
        <Pulse tone={status.tone} />
        <span className={cn('shrink-0 text-[0.8125rem] font-medium', WORD_CLASS[status.tone])}>{status.word}</span>
        {status.facts.map((fact) => <span key={fact} className="shrink-0 text-[0.75rem] text-muted-foreground tabular">{fact}</span>)}
        {tail && <span className="min-w-0 truncate text-[0.75rem] text-muted-foreground" title={tail}>{tail}</span>}
      </span>
      {status.hint && <span className="block truncate pl-[1.125rem] text-[0.75rem] text-muted-foreground" title={status.hint}>{status.hint}</span>}
    </span>
  )
}

/** 一把 key（外层 #265）：存了只露末四位，「换」展开一格粘贴、「删」按住才算；没存直接一格粘贴。
 *  key 存在平台的家里、只有本人能读，整把 key 从不回到页面 */
export function KeyField({ name, title, tail, ctx }: { name: string; title: string; tail?: string; ctx: Ctx }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')
  const save = () => void ctx.act(`key:${name}`, () => api.putKey(name, value)).then(() => { setValue(''); setEditing(false) })
  if (tail && !editing) {
    return (
      <>
        <Value className="mr-1.5">{tail}</Value>
        <Button variant="ghost" size="sm" disabled={ctx.busy !== null} onClick={() => setEditing(true)}>换</Button>
        <HoldButton disabled={ctx.busy !== null} onHold={() => void ctx.act(`key:${name}`, () => api.removeKey(name))}>删</HoldButton>
      </>
    )
  }
  return (
    <form className="flex items-center gap-1.5" onSubmit={(e) => { e.preventDefault(); if (value.trim()) save() }}>
      <Input type="password" value={value} onChange={(e) => setValue(e.target.value)} spellCheck={false} autoComplete="off"
             aria-label={`${title} 的 key`} placeholder={name.startsWith('custom') ? '粘贴这家的 key' : `粘贴 ${title} 的 key`} className="h-8 w-[15rem] max-w-full bg-card text-[0.8125rem]" />
      <Button type="submit" size="sm" disabled={ctx.busy !== null || !value.trim()}>存</Button>
      {tail && <Button type="button" variant="ghost" size="sm" onClick={() => { setValue(''); setEditing(false) }}>取消</Button>}
    </form>
  )
}
