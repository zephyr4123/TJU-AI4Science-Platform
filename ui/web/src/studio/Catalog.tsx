// 编辑台的「能力」镜头（P-21，外层 #112）：平台现在能做什么。一个阶段一行，七个阶段按序、最后「通用」一行（外层 #205）：
// 行里先是「步骤」，再是「skill」——能力的两个 tag 挂在同一个阶段下面，行前的标签说明是哪一种；skill 几百个，按 tag 分组
// （分类表在后端，`framework/skills/shelves.py`）。能力名横着排、满了折行，不横向滚（横着滚的一排后面的没人看）。空着的写「暂无」，
// 顶上一个查找对所有行生效。每个名字是一张小卡（SpotlightCard，与画布上的节点同一种材料，一看就是个东西），hover 是一行，
// 点了原地切成详情页：顶上一枚常驻的「能力」返回键，宋体大名与一行，底下参数与五栏，一列到底（主人：不要侧边目录）。
// 流程镜头里节点上的小片与配置板里的名字点了也跳到这里，一个详情两处入口。
// 层次与文件镜头同一做法：陈列印在雾景上不加框；详情才是一块抬起的面。对话窗浮在右边时（主人 2026-09-23：层级不能互相盖），
// 这一面按 useChatInset() 在右边留出板的宽度，详情居中在剩下的地方；关了板又铺满。
import { ArrowLeft, Toolbox } from '@phosphor-icons/react'
import { createElement, type ReactNode, useState } from 'react'

import { api } from '@/api/client'
import type { Capability, SkillEntry, StageInfo } from '@/api/types'
import { useChatInset } from '@/chat/ChatPanel'
import { ErrorNote, Skeleton } from '@/components/bits'
import { Markdown } from '@/components/Markdown'
import { SpotlightCard } from '@/components/reactbits/SpotlightCard'
import { Input } from '@/components/ui/input'
import { stageIcon } from '@/lib/stages'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

import { GENERAL, type ShelfRow, shelfRows } from './model'

/** 五栏的标题，顺序与后端 `COLUMNS` 一致（词表里的词） */
const COLUMNS: [keyof Pick<Capability, 'does' | 'does_not' | 'brings' | 'leaves' | 'stops'>, string][] = [
  ['does', '职责'], ['does_not', '边界'], ['brings', '输入'], ['leaves', '产出'], ['stops', '终止条件'],
]

export function Catalog({ stages, catalog, skills, focus, onFocus }: {
  stages: StageInfo[]; catalog: Capability[]; skills: SkillEntry[]; focus: string | null; onFocus: (name: string | null) => void
}) {
  const cap = focus ? catalog.find((c) => c.name === focus) ?? null : null
  const skill = focus && !cap ? skills.find((s) => s.name === focus) ?? null : null
  const inset = useChatInset()
  return (
    <div className="h-full overflow-y-auto transition-[padding] duration-200 ease-out motion-reduce:transition-none" style={{ paddingRight: inset }}>
      {cap
        ? <Detail key={cap.name} cap={cap} stage={stages.find((s) => s.name === cap.stage) ?? null} onBack={() => onFocus(null)} />
        : skill
          ? <SkillDetail key={skill.name} skill={skill} onBack={() => onFocus(null)} />
          : <Shelf stages={stages} catalog={catalog} skills={skills} onOpen={onFocus} />}
    </div>
  )
}

/** 陈列：一个阶段一行，标题是图标 + 宋体阶段名，底下「步骤」「skill」两行；印在雾景上，不加框 */
function Shelf({ stages, catalog, skills, onOpen }: {
  stages: StageInfo[]; catalog: Capability[]; skills: SkillEntry[]; onOpen: (name: string) => void
}) {
  const [query, setQuery] = useState('')
  const rows = shelfRows(stages.map((s) => s.name), catalog, skills, query)
  return (
    <div className="mx-auto max-w-[72rem] px-8 pt-8 pb-10">
      <div className="flex justify-end">
        <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="查找" aria-label="查找能力"
               className="h-8 w-[16rem] bg-card/85 text-[0.875rem] backdrop-blur-sm" />
      </div>
      {rows.length === 0
        ? <p className="mt-6 px-3 py-2.5 text-[0.9375rem] text-muted-foreground/70">没有对得上的</p>
        : <div className="mt-2">{rows.map((row) => <Row key={row.stage} row={row} searching={query.trim() !== ''} onOpen={onOpen} />)}</div>}
    </div>
  )
}

/** 一个阶段（或「通用」）一行。「通用」只有 skill：步骤都属于某个研究阶段 */
function Row({ row, searching, onOpen }: { row: ShelfRow; searching: boolean; onOpen: (name: string) => void }) {
  const icon = row.stage === GENERAL ? Toolbox : stageIcon(row.stage)
  const showSteps = row.stage !== GENERAL && (!searching || row.steps.length > 0)
  const showSkills = !searching || row.tags.length > 0
  return (
    <section aria-label={row.stage} className="py-5">
      <h2 className="flex items-center gap-2 font-serif text-[1.125rem] font-semibold">
        {createElement(icon, { weight: 'duotone', 'aria-hidden': true, className: 'size-[1.25rem] text-primary' })}
        {row.stage}
      </h2>
      {/* 内容与标题的字对齐（图标 1.25rem + 间距 0.5rem），整行宽度都给卡 */}
      <div className="mt-3 min-w-0 space-y-3 sm:pl-7">
        {showSteps && (
          <Line label="步骤">
            {row.steps.length === 0
              ? <Empty />
              : (
                <ul className="flex flex-wrap gap-2">
                  {row.steps.map((cap) => (
                    <Card key={cap.name} title={cap.title} brief={cap.brief} onOpen={() => onOpen(cap.name)}
                          icon={createElement(stageIcon(cap.stage), { weight: 'duotone', 'aria-hidden': true, className: 'size-4 shrink-0 text-primary' })} />
                  ))}
                </ul>
              )}
          </Line>
        )}
        {showSkills && (
          <Line label="skill">
            {row.tags.length === 0
              ? <Empty />
              : (
                <div className="space-y-2.5">
                  {row.tags.map((group) => (
                    <div key={group.tag} className="grid gap-x-3 gap-y-1.5 sm:grid-cols-[6.5rem_1fr]">
                      <h3 className="flex items-baseline gap-1.5 text-[0.8125rem] text-muted-foreground sm:pt-1.5">
                        {group.tag}<span className="text-[0.6875rem] tabular-nums text-muted-foreground/70">{group.skills.length}</span>
                      </h3>
                      <ul className="flex min-w-0 flex-wrap gap-1.5">
                        {group.skills.map((skill) => <Card key={skill.name} title={skill.title} brief={skill.brief} onOpen={() => onOpen(skill.name)} small />)}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
          </Line>
        )}
      </div>
    </section>
  )
}

/** 行里的一行：前面是 tag 的名（步骤 / skill），后面是内容 */
function Line({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[3rem_1fr] items-start gap-x-3">
      <span className="t-label pt-2">{label}</span>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

function Empty() {
  return <p className="py-1.5 text-[0.9375rem] text-muted-foreground/70">暂无</p>
}

/** 陈列里的一张小卡：名字（步骤带阶段图标），hover 一行；宽度跟着名字走，不截断。skill 多，卡小一号 */
function Card({ title, brief, icon, small = false, onOpen }: { title: string; brief: string; icon?: ReactNode; small?: boolean; onOpen: () => void }) {
  return (
    <li>
      <button type="button" onClick={onOpen} title={brief}
              className="group block rounded-2xl text-left transition-transform hover:-translate-y-px focus-visible:outline-2 focus-visible:outline-ring">
        <SpotlightCard spotlight="color-mix(in oklab, var(--primary) 16%, transparent)"
                       className={cn('border-transparent bg-card/85 shadow-sm ring-1 ring-foreground/[0.06] backdrop-blur-sm transition-[border-color,box-shadow] group-hover:border-primary/40',
                                     small && 'rounded-xl')}>
          <span className={cn('flex items-center gap-2 whitespace-nowrap', small ? 'px-3 py-1.5 text-[0.875rem]' : 'px-3.5 py-2.5 text-[0.9375rem] font-medium')}>
            {icon}
            {title}
          </span>
        </SpotlightCard>
      </button>
    </li>
  )
}

/** skill 的详情：SKILL.md 就是它的说明书——名、一行、脚本名，正文原样排（清单不带正文，按名字取） */
function SkillDetail({ skill, onBack }: { skill: SkillEntry; onBack: () => void }) {
  const doc = useResource(() => api.skill(skill.name), [skill.name], `skill:${skill.name}`)
  return (
    <article className="mx-auto my-3 max-w-[50rem] rounded-2xl bg-card shadow-[0_1px_2px_rgb(0_0_0/0.05),0_18px_44px_-22px_rgb(0_0_0/0.28)] ring-1 ring-foreground/[0.06]">
      <div className="sticky top-0 z-10 flex items-center gap-3 rounded-t-2xl bg-card/90 px-6 py-3 backdrop-blur-sm">
        <button type="button" onClick={onBack}
                className="inline-flex h-8 items-center gap-1.5 rounded-full border bg-card pr-3.5 pl-2.5 text-[0.8125rem] font-medium shadow-sm transition-colors hover:border-primary/50 hover:text-primary focus-visible:outline-2 focus-visible:outline-ring">
          <ArrowLeft aria-hidden className="size-3.5" />能力
        </button>
        <span className="flex items-center gap-1.5 text-[0.8125rem] text-muted-foreground">
          <Toolbox weight="duotone" aria-hidden className="size-4 text-foreground/60" />
          skill
        </span>
      </div>
      <header className="px-8 pt-3 pb-2">
        <h1 className="font-serif text-[2rem] leading-tight font-semibold tracking-tight">{skill.title}</h1>
        <p className="mt-2 text-[1.0625rem] text-muted-foreground">{skill.brief}</p>
        <p className="t-label mt-3 flex flex-wrap gap-x-4">
          <span>{skill.stage}·{skill.tag}</span>
          {skill.scripts.map((name) => <span key={name}>{name}</span>)}
          {skill.used_by.length > 0 && <span>用在 {skill.used_by.join('、')}</span>}
        </p>
      </header>
      <div className="px-8 pt-2 pb-10">
        {doc.data && <Markdown text={doc.data.body} />}
        {!doc.data && (doc.error ? <ErrorNote text={doc.error} /> : <Skeleton lines={6} />)}
      </div>
    </article>
  )
}

/** 详情页：常驻返回键、名与一行、参数、五栏，一列到底。「产出」那一栏前面先列本阶段的主文件（文件名是机器的名字，配页面上的名字） */
function Detail({ cap, stage, onBack }: { cap: Capability; stage: StageInfo | null; onBack: () => void }) {
  const mains = stage?.main_files ?? []
  return (
    <article className="mx-auto my-3 max-w-[50rem] rounded-2xl bg-card shadow-[0_1px_2px_rgb(0_0_0/0.05),0_18px_44px_-22px_rgb(0_0_0/0.28)] ring-1 ring-foreground/[0.06]">
      {/* 常驻的返回键：钉在板的顶上，滚到哪都在 */}
      <div className="sticky top-0 z-10 flex items-center gap-3 rounded-t-2xl bg-card/90 px-6 py-3 backdrop-blur-sm">
        <button type="button" onClick={onBack}
                className="inline-flex h-8 items-center gap-1.5 rounded-full border bg-card pr-3.5 pl-2.5 text-[0.8125rem] font-medium shadow-sm transition-colors hover:border-primary/50 hover:text-primary focus-visible:outline-2 focus-visible:outline-ring">
          <ArrowLeft aria-hidden className="size-3.5" />能力
        </button>
        <span className="flex items-center gap-1.5 text-[0.8125rem] text-muted-foreground">
          {createElement(stageIcon(cap.stage), { weight: 'duotone', 'aria-hidden': true, className: 'size-4 text-primary' })}
          {cap.stage}
        </span>
      </div>
      <header className="px-8 pt-3 pb-2">
        <h1 className="font-serif text-[2rem] leading-tight font-semibold tracking-tight">{cap.title}</h1>
        <p className="mt-2 text-[1.0625rem] text-muted-foreground">{cap.brief}</p>
      </header>
      <div className="px-8 pt-4 pb-10">
        <div className="min-w-0">
          {cap.params.length > 0 && (
            <section aria-label="参数" className="pt-2">
              <h2 className="t-step">参数</h2>
              <dl className="mt-3 grid grid-cols-[8rem_1fr] gap-x-4 gap-y-2 text-[0.9375rem]">
                {cap.params.map((p) => (
                  <div key={p.name} className="contents">
                    <dt className="font-medium">{p.label}</dt>
                    <dd className="text-muted-foreground">
                      {p.help}
                      {p.type !== 'bool' && p.default !== null && p.default !== undefined && p.default !== '' && (
                        <span className="ml-2 tabular-nums">缺省 {String(p.default)}</span>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          )}
          {COLUMNS.map(([key, label]) => (
            <section key={key} aria-label={label} className="pt-8 first:pt-2">
              <h2 className="t-step">{label}</h2>
              {key === 'leaves' && mains.length > 0 && (
                <p className="mt-3 text-[0.9375rem]">
                  <span className="text-muted-foreground">主文件</span>
                  {mains.map((f) => <span key={f.name} className="ml-3">{f.label} <span className="text-muted-foreground">{f.name}</span></span>)}
                </p>
              )}
              <p className="t-body mt-3">{cap[key]}</p>
            </section>
          ))}
        </div>
      </div>
    </article>
  )
}
