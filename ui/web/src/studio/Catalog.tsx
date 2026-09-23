// 编辑台的「能力」镜头（P-21，外层 #112）：平台现在能做什么。按七个阶段陈列步骤的名字——一个阶段挂再多也只是名字的清单，
// 空着的阶段老实写「暂无」；第八列是 skill（能力的另一个 tag，主人 2026-09-22）：哪个阶段都能挂，所以不归在某一列下；每个名字是一张小卡（SpotlightCard，与画布上的节点同一种材料，一看就是个东西），hover 是一行，
// 点了原地切成详情页：顶上一枚常驻的「能力」返回键，宋体大名与一行，底下参数与五栏，一列到底（主人：不要侧边目录）。
// 流程镜头里节点上的小片与配置板里的名字点了也跳到这里，一个详情两处入口。
// 层次与文件镜头同一做法：陈列印在雾景上不加框；详情才是一块抬起的面。对话窗浮在右边时（主人 2026-09-23：层级不能互相盖），
// 这一面按 useChatInset() 在右边留出板的宽度，列自动折到下面、详情居中在剩下的地方；关了板又铺满。
import { ArrowLeft, Toolbox } from '@phosphor-icons/react'
import { createElement, type ReactNode } from 'react'

import type { Capability, SkillEntry, StageInfo } from '@/api/types'
import { useChatInset } from '@/chat/ChatPanel'
import { Markdown } from '@/components/Markdown'
import { SpotlightCard } from '@/components/reactbits/SpotlightCard'
import { groupByStage, stageIcon } from '@/lib/stages'

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

/** 陈列：七列步骤（列头阶段图标 + 宋体阶段名）+ 第八列 skill，底下一张一张小卡；印在雾景上，不加框 */
function Shelf({ stages, catalog, skills, onOpen }: {
  stages: StageInfo[]; catalog: Capability[]; skills: SkillEntry[]; onOpen: (name: string) => void
}) {
  const groups = groupByStage(stages.map((s) => s.name), catalog)
  return (
    <div className="mx-auto grid max-w-[96rem] grid-cols-[repeat(auto-fill,minmax(11rem,1fr))] gap-x-4 gap-y-8 px-8 pt-10 pb-8" aria-label="能力">
      {groups.map((group) => (
        <section key={group.stage} aria-label={group.stage}>
          <h2 className="flex items-center gap-2 font-serif text-[1.0625rem] font-semibold">
            {createElement(stageIcon(group.stage), { weight: 'duotone', 'aria-hidden': true, className: 'size-[1.25rem] text-primary' })}
            {group.stage}
          </h2>
          {group.caps.length === 0
            ? <p className="mt-3 px-3 py-2.5 text-[0.9375rem] text-muted-foreground/70">暂无</p>
            : (
              <ul className="mt-3 space-y-2">
                {group.caps.map((cap) => (
                  <Card key={cap.name} title={cap.title} brief={cap.brief} onOpen={() => onOpen(cap.name)}
                        icon={createElement(stageIcon(cap.stage), { weight: 'duotone', 'aria-hidden': true, className: 'size-4 shrink-0 text-primary' })} />
                ))}
              </ul>
            )}
        </section>
      ))}
      <section aria-label="skill">
        <h2 className="flex items-center gap-2 font-serif text-[1.0625rem] font-semibold">
          <Toolbox weight="duotone" aria-hidden className="size-[1.25rem] text-foreground/70" />
          skill
        </h2>
        {skills.length === 0
          ? <p className="mt-3 px-3 py-2.5 text-[0.9375rem] text-muted-foreground/70">暂无</p>
          : (
            <ul className="mt-3 space-y-2">
              {skills.map((skill) => (
                <Card key={skill.name} title={skill.title} brief={skill.brief} onOpen={() => onOpen(skill.name)}
                      icon={<Toolbox weight="duotone" aria-hidden className="size-4 shrink-0 text-foreground/60" />} />
              ))}
            </ul>
          )}
      </section>
    </div>
  )
}

/** 陈列里的一张小卡：图标 + 名，hover 一行 */
function Card({ title, brief, icon, onOpen }: { title: string; brief: string; icon: ReactNode; onOpen: () => void }) {
  return (
    <li>
      <button type="button" onClick={onOpen} title={brief}
              className="group block w-full rounded-2xl text-left transition-transform hover:-translate-y-px focus-visible:outline-2 focus-visible:outline-ring">
        <SpotlightCard spotlight="color-mix(in oklab, var(--primary) 16%, transparent)"
                       className="border-transparent bg-card/85 shadow-sm ring-1 ring-foreground/[0.06] backdrop-blur-sm transition-[border-color,box-shadow] group-hover:border-primary/40">
          <span className="flex items-center gap-2 px-3.5 py-2.5">
            {icon}
            <span className="min-w-0 flex-1 truncate text-[0.9375rem] font-medium">{title}</span>
          </span>
        </SpotlightCard>
      </button>
    </li>
  )
}

/** skill 的详情：SKILL.md 就是它的说明书——名、一行、脚本名，正文原样排 */
function SkillDetail({ skill, onBack }: { skill: SkillEntry; onBack: () => void }) {
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
          <span>{skill.library === 'generic' ? '通用' : skill.library}</span>
          {skill.scripts.map((name) => <span key={name}>{name}</span>)}
          {skill.used_by.length > 0 && <span>用在 {skill.used_by.join('、')}</span>}
        </p>
      </header>
      <div className="px-8 pt-2 pb-10">
        <Markdown text={skill.body} />
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
