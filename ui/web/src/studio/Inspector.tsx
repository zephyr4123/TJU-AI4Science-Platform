// 选中节点的配置。阶段：这个阶段有哪些能力，勾上就点名，参数按描述符逐个给输入框（能力参数在页面上的落点，外层 #101）；
// 断点：先选是哪种——发布、验收（框架守着的两个，各有记录，助理没它不开下一步）还是别的（写一句确认事项，助理停下来等人说继续）。
// 五列说明折在展开层里，不占面板。
import { CaretDown, HandPalm, Signature, Stamp } from '@phosphor-icons/react'
import { createElement, useState } from 'react'

import type { Capability, CapabilityParam } from '@/api/types'
import SquishSwitch from '@/components/reactbits/SquishSwitch'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { LEVEL_COPY } from '@/lib/humanize'
import { actorOf, stageIcon } from '@/lib/stages'
import { cn } from '@/lib/utils'

import { type Item, parseParam, setParam, type StageItem, type StopItem, toggleCap } from './model'

/** 五列的标题，顺序与后端 `COLUMNS` 一致 */
const COLUMNS: [keyof Pick<Capability, 'does' | 'does_not' | 'brings' | 'leaves' | 'stops'>, string][] = [
  ['does', '干什么'], ['does_not', '不干什么'], ['brings', '要带什么进来'], ['leaves', '留下什么'], ['stops', '什么时候停'],
]

export function Inspector({ item, catalog, onChange }: { item: Item; catalog: Capability[]; onChange: (item: Item) => void }) {
  if (item.kind === 'stop') return <StopPanel item={item} onChange={onChange} />
  return <StagePanel item={item} caps={catalog.filter((c) => c.stage === item.stage)} onChange={onChange} />
}

function StagePanel({ item, caps, onChange }: { item: StageItem; caps: Capability[]; onChange: (item: StageItem) => void }) {
  return (
    <div>
      <h2 className="flex items-center gap-2 font-serif text-[1.0625rem] font-semibold">
        {createElement(stageIcon(item.stage), { weight: 'duotone', 'aria-hidden': true, className: 'size-[1.125rem] text-primary' })}
        {item.stage}
      </h2>
      {caps.length === 0
        ? <p className="mt-3 text-[0.8125rem] text-muted-foreground">暂无能力</p>
        : (
          <ul className="mt-3 space-y-2">
            {caps.map((cap) => {
              const pick = item.caps.find((p) => p.cap === cap.name)
              return (
                <CapRow key={cap.name} cap={cap} picked={pick?.with ?? null}
                        onToggle={(on) => onChange(toggleCap(item, cap.name, on))}
                        onParam={(name, value) => onChange(setParam(item, cap.name, name, value))} />
              )
            })}
          </ul>
        )}
    </div>
  )
}

/** 一颗能力：勾选、参数、展开五列 */
function CapRow({ cap, picked, onToggle, onParam }: {
  cap: Capability; picked: Record<string, unknown> | null
  onToggle: (on: boolean) => void; onParam: (name: string, value: unknown) => void
}) {
  const [open, setOpen] = useState(false)
  const id = `cap-${cap.name}`
  // 流里能写的参数才给输入框；每次调用时才定的（run_id、resume）不在这儿
  const knobs = cap.params.filter((p) => p.in_flow !== false)
  return (
    <li className={cn('rounded-xl border', picked ? 'border-primary/50 bg-card' : 'bg-card/60')}>
      <div className="flex items-center gap-2.5 px-3 py-2.5">
        <Checkbox id={id} checked={picked !== null} onCheckedChange={(v) => onToggle(v === true)} />
        <label htmlFor={id} className="min-w-0 flex-1 cursor-pointer">
          <span className="block truncate text-[0.9375rem] font-medium">{cap.title}</span>
          <span className="block text-[0.75rem] text-muted-foreground">{actorOf(cap)} · {LEVEL_COPY[cap.level]}</span>
        </label>
        <button type="button" aria-label={open ? '收起' : '说明'} aria-expanded={open} onClick={() => setOpen((v) => !v)}
                className="grid size-7 shrink-0 place-items-center rounded-md text-muted-foreground hover:bg-accent/40 hover:text-foreground">
          <CaretDown className={cn('size-3.5 transition-transform duration-200', open && 'rotate-180')} />
        </button>
      </div>
      {picked && knobs.length > 0 && (
        <dl className="space-y-2 border-t px-3 py-2.5">
          {knobs.map((p) => <ParamField key={p.name} param={p} value={picked[p.name]} onChange={(v) => onParam(p.name, v)} />)}
        </dl>
      )}
      {open && (
        <dl className="space-y-2 border-t px-3 py-2.5 text-[0.75rem] leading-relaxed">
          {COLUMNS.map(([key, label]) => (
            <div key={key}>
              <dt className="font-medium text-foreground">{label}</dt>
              <dd className="text-muted-foreground">{cap[key]}</dd>
            </div>
          ))}
        </dl>
      )}
    </li>
  )
}

/** 一个参数：布尔是开关，数字与字符串是输入框；空着就是描述符的缺省值 */
function ParamField({ param, value, onChange }: { param: CapabilityParam; value: unknown; onChange: (value: unknown) => void }) {
  const fallback = param.default === null || param.default === undefined || param.default === '' ? '' : String(param.default)
  if (param.type === 'bool') {
    return (
      <div className="flex items-center justify-between gap-3">
        <dt className="font-mono text-[0.75rem]" title={param.help}>{param.name}</dt>
        <dd><SquishSwitch checked={value === true} onChange={(on) => onChange(on ? true : undefined)} ariaLabel={param.name} width={32} height={18} /></dd>
      </div>
    )
  }
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="min-w-0 truncate font-mono text-[0.75rem]" title={param.help}>{param.name}</dt>
      <dd className="w-[7.5rem] shrink-0">
        <Input value={value === undefined ? '' : String(value)} placeholder={fallback} aria-label={param.name} title={param.help}
               inputMode={param.type === 'str' ? 'text' : 'decimal'} className="h-7 bg-card font-mono text-[0.75rem]"
               onChange={(e) => onChange(parseParam(param.type, e.target.value))} />
      </dd>
    </div>
  )
}

const STOP_KINDS = [
  { key: '发布', icon: Stamp, hint: '记录：publish.json；没它评分脚本与实验不开' },
  { key: '验收', icon: Signature, hint: '记录：accept.json；签这一版 best 与验证结论' },
  { key: '', icon: HandPalm, hint: '写一句确认事项；助理停下来等人说继续' },
] as const

function StopPanel({ item, onChange }: { item: StopItem; onChange: (item: StopItem) => void }) {
  const kind = item.note === '发布' || item.note === '验收' ? item.note : ''
  return (
    <div>
      <h2 className="flex items-center gap-2 font-serif text-[1.0625rem] font-semibold text-wait"><HandPalm weight="duotone" className="size-[1.125rem]" />断点</h2>
      <div role="radiogroup" aria-label="断点种类" className="mt-3 grid grid-cols-3 gap-1.5">
        {STOP_KINDS.map(({ key, icon }) => (
          <Button key={key || 'other'} size="sm" role="radio" aria-checked={kind === key} title={STOP_KINDS.find((k) => k.key === key)?.hint}
                  variant={kind === key ? 'default' : 'outline'} onClick={() => onChange({ ...item, note: key })}>
            {createElement(icon, { weight: 'duotone', 'aria-hidden': true })}{key || '其它'}
          </Button>
        ))}
      </div>
      <p className="mt-2 text-[0.75rem] text-muted-foreground">{STOP_KINDS.find((k) => k.key === kind)?.hint}</p>
      {kind === '' && (
        <Input value={item.note} placeholder="确认事项" aria-label="确认事项" className="mt-2 bg-card"
               onChange={(e) => onChange({ ...item, note: e.target.value })} />
      )}
    </div>
  )
}
