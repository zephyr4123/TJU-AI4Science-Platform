// 编辑台的「能力」镜头（P-21，外层 #112）：平台现在能做什么。按七个阶段陈列名字——一个阶段挂再多能力也只是名字的清单，
// 空着的阶段老实写「暂无」；名字 hover 是一行，点了原地切成详情页（面包屑「能力 › 名」）：一行、参数、五栏。
// 流程镜头里节点上的小片与配置板里的名字点了也跳到这里，一个详情两处入口。
// 层次与文件镜头同一做法：陈列是索引，直接印在雾景上不加框；详情才是一块抬起的面。
import { CaretRight } from '@phosphor-icons/react'
import { createElement } from 'react'

import type { Capability, StageInfo } from '@/api/types'
import { groupByStage, stageIcon } from '@/lib/stages'

/** 五栏的标题，顺序与后端 `COLUMNS` 一致（词表里的词） */
const COLUMNS: [keyof Pick<Capability, 'does' | 'does_not' | 'brings' | 'leaves' | 'stops'>, string][] = [
  ['does', '职责'], ['does_not', '边界'], ['brings', '输入'], ['leaves', '产出'], ['stops', '终止条件'],
]

export function Catalog({ stages, catalog, focus, onFocus }: {
  stages: StageInfo[]; catalog: Capability[]; focus: string | null; onFocus: (name: string | null) => void
}) {
  const cap = focus ? catalog.find((c) => c.name === focus) ?? null : null
  return (
    <div className="h-full overflow-y-auto">
      {cap
        ? (
          <div className="mx-auto my-3 max-w-[50rem] rounded-2xl bg-card shadow-[0_1px_2px_rgb(0_0_0/0.05),0_18px_44px_-22px_rgb(0_0_0/0.28)] ring-1 ring-foreground/[0.06]">
            <Detail cap={cap} stage={stages.find((s) => s.name === cap.stage) ?? null} onBack={() => onFocus(null)} />
          </div>
        )
        : <Shelf stages={stages} catalog={catalog} onOpen={onFocus} />}
    </div>
  )
}

/** 陈列：七列，列头阶段图标 + 宋体阶段名，底下一行一个名字；印在雾景上，不加框 */
function Shelf({ stages, catalog, onOpen }: { stages: StageInfo[]; catalog: Capability[]; onOpen: (name: string) => void }) {
  const groups = groupByStage(stages.map((s) => s.name), catalog)
  return (
    <div className="mx-auto grid max-w-[80rem] grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-x-4 gap-y-8 px-8 pt-10 pb-8" aria-label="能力">
      {groups.map((group) => (
        <section key={group.stage} aria-label={group.stage}>
          <h2 className="flex items-center gap-2 font-serif text-[1.0625rem] font-semibold">
            {createElement(stageIcon(group.stage), { weight: 'duotone', 'aria-hidden': true, className: 'size-[1.25rem] text-primary' })}
            {group.stage}
          </h2>
          {group.caps.length === 0
            ? <p className="mt-3 py-1.5 text-[0.9375rem] text-muted-foreground/70">暂无</p>
            : (
              <ul className="mt-3 space-y-1">
                {group.caps.map((cap) => (
                  <li key={cap.name}>
                    <button type="button" onClick={() => onOpen(cap.name)} title={cap.brief}
                            className="group -mx-2 flex w-[calc(100%+1rem)] items-center gap-1 rounded-lg px-2 py-1.5 text-left text-[0.9375rem] font-medium transition-colors hover:bg-accent/60 hover:text-primary focus-visible:outline-2 focus-visible:outline-ring">
                      <span className="min-w-0 flex-1 truncate">{cap.title}</span>
                      <CaretRight aria-hidden className="size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
        </section>
      ))}
    </div>
  )
}

/** 详情页：面包屑、名、一行、参数、五栏。「产出」那一栏前面先列本阶段的主文件（文件名是机器的名字，配页面上的名字） */
function Detail({ cap, stage, onBack }: { cap: Capability; stage: StageInfo | null; onBack: () => void }) {
  const mains = stage?.main_files ?? []
  return (
    <article className="mx-auto max-w-[46rem] px-7 py-7">
      <nav aria-label="位置" className="flex items-center gap-1.5 text-[0.875rem] text-muted-foreground">
        <button type="button" onClick={onBack} className="rounded-md px-1 hover:text-primary focus-visible:outline-2 focus-visible:outline-ring">能力</button>
        <CaretRight aria-hidden className="size-3" />
        <span className="flex items-center gap-1.5 text-foreground">
          {createElement(stageIcon(cap.stage), { weight: 'duotone', 'aria-hidden': true, className: 'size-4 text-primary' })}
          {cap.stage}
        </span>
      </nav>
      <h1 className="mt-4 font-serif text-[1.75rem] leading-tight font-semibold tracking-tight">{cap.title}</h1>
      <p className="mt-2 text-[1rem] text-muted-foreground">{cap.brief}</p>
      {cap.params.length > 0 && (
        <section className="mt-7" aria-label="参数">
          <h2 className="t-step">参数</h2>
          <dl className="mt-2 grid grid-cols-[8rem_1fr] gap-x-4 gap-y-1.5 text-[0.9375rem]">
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
        <section key={key} className="mt-7" aria-label={label}>
          <h2 className="t-step">{label}</h2>
          {key === 'leaves' && mains.length > 0 && (
            <p className="mt-2 text-[0.9375rem]">
              <span className="text-muted-foreground">主文件</span>
              {mains.map((f) => <span key={f.name} className="ml-3">{f.label} <span className="text-muted-foreground">{f.name}</span></span>)}
            </p>
          )}
          <p className="t-body mt-2">{cap[key]}</p>
        </section>
      ))}
    </article>
  )
}
