// 选中节点的配置。阶段：这个阶段有哪些能力，勾上就点名，参数按描述符逐个给输入框（能力参数在页面上的落点，外层 #101）；
// 断点：写一句确认事项（上游产出经人确认后下游方可读取；几个、放哪由流程定，P-19）。
// 能力这一行只有名字与参数（P-21 三层对三种动作）：一行 hover 看，详情点名字跳到「能力」镜头的详情页，这里不摊开。
import { CaretRight, Signature } from '@phosphor-icons/react'
import { createElement } from 'react'

import type { Capability, CapabilityParam, SkillEntry } from '@/api/types'
import SquishSwitch from '@/components/reactbits/SquishSwitch'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { stageIcon } from '@/lib/stages'
import { cn } from '@/lib/utils'

import { type Item, parseParam, setParam, type StageItem, type StopItem, toggleCap } from './model'

export function Inspector({ item, catalog, skills, onChange, onOpenCap }: {
  item: Item; catalog: Capability[]; skills: SkillEntry[]; onChange: (item: Item) => void; onOpenCap: (name: string) => void
}) {
  if (item.kind === 'stop') return <StopPanel item={item} onChange={onChange} />
  return <StagePanel item={item} caps={catalog.filter((c) => c.stage === item.stage)} skills={skills} onChange={onChange} onOpenCap={onOpenCap} />
}

/** 阶段面板两段，段名就是 tag：步骤（这个阶段的，勾上就点名、带参数）、skill（哪个阶段都能挂，勾上就挂、没有参数） */
function StagePanel({ item, caps, skills, onChange, onOpenCap }: {
  item: StageItem; caps: Capability[]; skills: SkillEntry[]; onChange: (item: StageItem) => void; onOpenCap: (name: string) => void
}) {
  return (
    <div>
      <h2 className="flex items-center gap-2 font-serif text-[1.0625rem] font-semibold">
        {createElement(stageIcon(item.stage), { weight: 'duotone', 'aria-hidden': true, className: 'size-[1.125rem] text-primary' })}
        {item.stage}
      </h2>
      <h3 className="mt-3 text-[0.75rem] text-muted-foreground">步骤</h3>
      {caps.length === 0
        ? <p className="mt-1.5 text-[0.8125rem] text-muted-foreground/70">无</p>
        : (
          <ul className="mt-1.5 space-y-2">
            {caps.map((cap) => {
              const pick = item.caps.find((p) => p.cap === cap.name)
              return (
                <CapRow key={cap.name} cap={cap} picked={pick?.with ?? null}
                        onToggle={(on) => onChange(toggleCap(item, cap.name, on))}
                        onParam={(name, value) => onChange(setParam(item, cap.name, name, value))}
                        onOpen={() => onOpenCap(cap.name)} />
              )
            })}
          </ul>
        )}
      <h3 className="mt-4 text-[0.75rem] text-muted-foreground">skill</h3>
      {skills.length === 0
        ? <p className="mt-1.5 text-[0.8125rem] text-muted-foreground/70">无</p>
        : (
          <ul className="mt-1.5 space-y-2">
            {skills.map((skill) => (
              <SkillRow key={skill.name} skill={skill} picked={item.caps.some((p) => p.cap === skill.name)}
                        onToggle={(on) => onChange(toggleCap(item, skill.name, on))} onOpen={() => onOpenCap(skill.name)} />
            ))}
          </ul>
        )}
    </div>
  )
}

/** 一个 skill：勾选、名字（hover 一行、点了跳详情）；没有参数——它的参数在调用时给 */
function SkillRow({ skill, picked, onToggle, onOpen }: {
  skill: SkillEntry; picked: boolean; onToggle: (on: boolean) => void; onOpen: () => void
}) {
  const id = `skill-${skill.name}`
  return (
    <li className={cn('rounded-xl border', picked ? 'border-foreground/30 bg-card' : 'bg-card/60')}>
      <div className="flex items-center gap-2.5 px-3 py-2.5">
        <Checkbox id={id} checked={picked} onCheckedChange={(v) => onToggle(v === true)} aria-label={skill.title} />
        <button type="button" onClick={onOpen} title={skill.brief}
                className="group flex min-w-0 flex-1 items-center gap-1 text-left text-[0.9375rem] font-medium hover:text-primary focus-visible:outline-2 focus-visible:outline-ring">
          <span className="truncate">{skill.title}</span>
          <CaretRight aria-hidden className="size-3.5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
        </button>
      </div>
    </li>
  )
}

/** 一个能力：勾选、名字（hover 一行、点了跳详情）、勾上后的参数 */
function CapRow({ cap, picked, onToggle, onParam, onOpen }: {
  cap: Capability; picked: Record<string, unknown> | null
  onToggle: (on: boolean) => void; onParam: (name: string, value: unknown) => void; onOpen: () => void
}) {
  const id = `cap-${cap.name}`
  // 流程里能写的参数才给输入框；每次调用时才定的（续跑、修改意见）不在这儿
  const knobs = cap.params.filter((p) => p.in_flow !== false)
  return (
    <li className={cn('rounded-xl border', picked ? 'border-primary/50 bg-card' : 'bg-card/60')}>
      <div className="flex items-center gap-2.5 px-3 py-2.5">
        <Checkbox id={id} checked={picked !== null} onCheckedChange={(v) => onToggle(v === true)} aria-label={cap.title} />
        <button type="button" onClick={onOpen} title={cap.brief}
                className="group flex min-w-0 flex-1 items-center gap-1 text-left text-[0.9375rem] font-medium hover:text-primary focus-visible:outline-2 focus-visible:outline-ring">
          <span className="truncate">{cap.title}</span>
          <CaretRight aria-hidden className="size-3.5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
        </button>
      </div>
      {picked && knobs.length > 0 && (
        <dl className="space-y-2 border-t px-3 py-2.5">
          {knobs.map((p) => <ParamField key={p.name} param={p} value={picked[p.name]} onChange={(v) => onParam(p.name, v)} />)}
        </dl>
      )}
    </li>
  )
}

/** 一个参数：布尔是开关，数字与字符串是输入框；空着就是描述符的缺省值。名字是描述符给的 label，参数名不上屏 */
function ParamField({ param, value, onChange }: { param: CapabilityParam; value: unknown; onChange: (value: unknown) => void }) {
  const fallback = param.default === null || param.default === undefined || param.default === '' ? '' : String(param.default)
  if (param.type === 'bool') {
    return (
      <div className="flex items-center justify-between gap-3">
        <dt className="text-[0.8125rem]" title={param.help}>{param.label}</dt>
        <dd><SquishSwitch checked={value === true} onChange={(on) => onChange(on ? true : undefined)} ariaLabel={param.label} width={32} height={18} /></dd>
      </div>
    )
  }
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="min-w-0 truncate text-[0.8125rem]" title={param.help}>{param.label}</dt>
      <dd className="w-[7.5rem] shrink-0">
        <Input value={value === undefined ? '' : String(value)} placeholder={fallback} aria-label={param.label} title={param.help}
               inputMode={param.type === 'str' ? 'text' : 'decimal'} className="h-7 bg-card text-[0.8125rem] tabular-nums"
               onChange={(e) => onChange(parseParam(param.type, e.target.value))} />
      </dd>
    </div>
  )
}

function StopPanel({ item, onChange }: { item: StopItem; onChange: (item: StopItem) => void }) {
  return (
    <div>
      <h2 className="flex items-center gap-2 font-serif text-[1.0625rem] font-semibold text-wait"><Signature weight="duotone" className="size-[1.125rem]" />断点</h2>
      <p className="mt-2 text-[0.75rem] text-muted-foreground">上游产出经人确认后，下游方可读取。</p>
      <Input value={item.note} placeholder="确认事项" aria-label="确认事项" className="mt-2 bg-card"
             onChange={(e) => onChange({ ...item, note: e.target.value })} />
    </div>
  )
}
