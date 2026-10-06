// 需求确认之后的工作区页（外层 #255，主人 2026-10-06：原来一列一张卡、卡里再套卡，像堆积木）：一条流程一块抬起的面，
// 面里不再套框——流程是一条竖线，阶段与断点是线上的节点（走过 / 当前 / 没到），产出挂在阶段下面一行一条，名说全：
// 第几次、产出名、生成者、读取了哪次产出、时间、状态。阶段名旁一行小字是这一格计划的步骤与挂的 skill（计划），
// 下面的行才是实际跑出来的（实际），两样不混。一个阶段的产出多了只露最近两次，待确认与运行中的总露着。
// 题头右边一句话说在等谁；不在任何流程里的产出（包括记了流程却没记第几步的）都在最底下「单独运行」，一次都不漏。
import { ArrowRight, CaretDown, CaretUp, CheckCircle, Info, Signature, Trash, WarningCircle } from '@phosphor-icons/react'
import { createElement, type ReactNode, useState } from 'react'

import type { WorkspaceClient } from '@/api/client'
import type { FlowPick, FlowProgress, FlowProgressItem, OutputBrief, WorkspaceDetail } from '@/api/types'
import { Aurora, follow, Spot } from '@/components/Aurora'
import { Dot, ErrorNote, Problems } from '@/components/bits'
import HoldButton from '@/components/reactbits/HoldButton'
import { when } from '@/lib/format'
import { byWord } from '@/lib/humanize'
import { stageIcon } from '@/lib/stages'
import { cn } from '@/lib/utils'

import { fold, looseOutputs, type NameOf, needsSign, type OutputState, outputName, stageState, stateOf, stopState,
         tookWord, waitingSentence } from './derive'

/** 一个阶段计划了什么：流程在这一格点名的步骤、挂的 skill（名直接显示、一行 hover） */
export interface StagePlan { steps: Chip[]; skills: Chip[] }
export interface Chip { title: string; brief: string }

/** 一行产出要的几样名字：阶段名、别的工作区的名字、生成者（能力的标题） */
interface Names {
  stage: NameOf
  workspace: (id: string) => string | undefined
  cap: (name: string) => string | undefined
}

export function Flows({ workspace, doc, planOf, names, onOpen, onChanged }: {
  workspace: WorkspaceClient
  doc: WorkspaceDetail
  planOf: (picks: FlowPick[]) => StagePlan
  names: Names
  onOpen: (oid: string) => void
  onChanged: () => Promise<void>
}) {
  const pending = needsSign(doc.flows)
  const loose = looseOutputs(doc.stages, doc.flows)
  const brief = new Map(doc.stages.flatMap((s) => s.outputs.map((o) => [o.id, o] as const)))
  return (
    <div className="space-y-7">
      {doc.flows.length === 0 && <p className="t-label">尚未选定流程。与助理说明照哪条流程进行。</p>}
      {doc.flows.map((flow) => (
        <FlowPanel key={flow.name} workspace={workspace} flow={flow} pending={pending} brief={brief} planOf={planOf} names={names}
                   onOpen={onOpen} onChanged={onChanged} />
      ))}
      {loose.length > 0 && <Loose outputs={loose} pending={pending} names={names} onOpen={onOpen} />}
    </div>
  )
}

/** 一条流程一块面：题头（「流程」+ 宋体名、右边在等谁与停止 / 删除）、一道渐隐的细线、竖向时间线 */
function FlowPanel({ workspace, flow, pending, brief, planOf, names, onOpen, onChanged }: {
  workspace: WorkspaceClient; flow: FlowProgress; pending: Set<string>; brief: Map<string, OutputBrief>
  planOf: (picks: FlowPick[]) => StagePlan; names: Names; onOpen: (oid: string) => void; onChanged: () => Promise<void>
}) {
  const broken = flow.problems.length > 0 || !flow.items
  const items = flow.items ?? []
  return (
    <Aurora>
      <section aria-label={`流程「${flow.title}」`}>
        <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-6 pt-5 pb-4">
          <h2 className="flex min-w-0 items-baseline gap-2">
            <span className="shrink-0 text-[0.8125rem] text-muted-foreground">流程</span>
            <span className="truncate font-serif text-[1.1875rem] leading-tight font-semibold">{flow.title}</span>
          </h2>
          <span className="flex items-center gap-3">
            <FlowStatus flow={flow} pending={pending} names={names} broken={broken} />
            {flow.waiting === 'job' && flow.job && <StopKey workspace={workspace} jobId={flow.job.job_id} onChanged={onChanged} />}
            {!flow.job && !items.some((i) => i.outputs.length > 0) && (
              <RemoveFlowKey workspace={workspace} name={flow.name} onChanged={onChanged} />
            )}
          </span>
        </header>
        <div aria-hidden="true" className="mx-6 h-px bg-[linear-gradient(90deg,transparent,color-mix(in_oklab,var(--foreground)_12%,transparent)_12%,color-mix(in_oklab,var(--foreground)_12%,transparent)_88%,transparent)]" />
        {broken ? <div className="px-6 py-5"><Problems items={flow.problems} /></div> : (
          <ol className="px-6 pt-5 pb-4" aria-label="流程的每一项">
            {items.map((item, i) => item.kind === 'stage'
              ? <StageNode key={item.index} item={item} flow={flow} last={i === items.length - 1} pending={pending} brief={brief}
                           plan={planOf(item.caps)} names={names} onOpen={onOpen} />
              : <StopNode key={item.index} item={item} flow={flow} last={i === items.length - 1} />)}
          </ol>
        )}
      </section>
    </Aurora>
  )
}

/** 题头右边那句话：完成（铜绿带勾）/ 待确认（琥珀软底）/ 运行中（靛、呼吸点）/ 下一步（靛）/ 流程文件有误（红） */
function FlowStatus({ flow, pending, names, broken }: { flow: FlowProgress; pending: Set<string>; names: Names; broken: boolean }) {
  const sentence = waitingSentence(flow, pending, names.stage)
  if (broken) return <span className="flex items-center gap-1.5 text-[0.875rem] text-bad"><WarningCircle className="size-4" aria-hidden />{sentence}</span>
  if (flow.waiting === 'sign') {
    return <span className="flex items-center gap-1.5 rounded-full bg-wait-soft px-3 py-1 text-[0.8125rem] font-semibold text-wait"><Signature weight="fill" className="size-4" aria-hidden />{sentence}</span>
  }
  if (flow.waiting === 'job') return <span className="flex items-center gap-2 text-[0.875rem] text-primary"><Dot tone="primary" pulse />{sentence}</span>
  if (flow.waiting === 'assistant') return <span className="flex items-center gap-1.5 text-[0.875rem] text-primary"><ArrowRight className="size-4" aria-hidden />{sentence}</span>
  return <span className="flex items-center gap-1.5 text-[0.875rem] text-ok"><CheckCircle weight="fill" className="size-4" aria-hidden />{sentence}</span>
}

/** 时间线的一项：左边一条竖轨（节点 + 往下接到下一个节点的线，走过的实线、没到的虚线，与上下节点各留一道缝），右边是内容。
 *  项与项的间距放在内容里，竖轨那一格才撑满整项、线接得上 */
function Rail({ node, line, children }: { node: ReactNode; line: 'solid' | 'dashed' | null; children: ReactNode }) {
  return (
    <li className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-3.5">
      <div className="relative flex justify-center">
        <div className="relative z-10 flex h-7 items-center">{node}</div>
        {line && (
          <span aria-hidden="true"
                className={cn('absolute top-[2.125rem] bottom-1.5 left-1/2 w-px -translate-x-1/2',
                              line === 'solid' ? 'bg-foreground/20'
                                : 'bg-[repeating-linear-gradient(to_bottom,color-mix(in_oklab,var(--foreground)_24%,transparent)_0_3px,transparent_3px_7px)]')} />
        )}
      </div>
      <div className={cn('min-w-0', line && 'pb-5')}>{children}</div>
    </li>
  )
}

/** 一个阶段：节点是阶段的图标（走过 墨色软底 / 当前 靛底白字带一圈光、在跑时外圈慢慢涨开 / 没到 虚线圈），
 *  宋体「X阶段」+ 计划那一行，下面是实际的产出 */
function StageNode({ item, flow, last, pending, brief, plan, names, onOpen }: {
  item: Extract<FlowProgressItem, { kind: 'stage' }>; flow: FlowProgress; last: boolean; pending: Set<string>
  brief: Map<string, OutputBrief>; plan: StagePlan; names: Names; onOpen: (oid: string) => void
}) {
  const state = stageState(item, flow)
  const outputs = item.outputs.map((o) => brief.get(o.id)).filter((o): o is OutputBrief => o !== undefined)
  const running = flow.waiting === 'job' && state === 'current'
  const runningElsewhere = running && !item.outputs.some((o) => o.id === flow.job?.output)
  return (
    <Rail line={last ? null : state === 'todo' ? 'dashed' : 'solid'}
          node={
            <span className={cn('relative flex size-7 items-center justify-center rounded-full',
                                state === 'done' && 'bg-card text-foreground/70 shadow-[0_1px_2px_rgb(0_0_0/0.06)] ring-1 ring-foreground/[0.12]',
                                state === 'current' && 'bg-primary text-primary-foreground shadow-[0_0_0_5px_color-mix(in_oklab,var(--primary)_16%,transparent),0_6px_16px_-6px_var(--primary)]',
                                state === 'todo' && 'border border-dashed border-foreground/25 text-muted-foreground/70')}>
              {running && <span aria-hidden="true" className="absolute inset-0 rounded-full bg-primary/40 motion-safe:animate-ping" />}
              {createElement(stageIcon(item.stage), { weight: state === 'current' ? 'fill' : 'duotone', 'aria-hidden': true, className: 'relative size-4' })}
            </span>
          }>
      <div className="flex min-h-7 flex-wrap items-baseline gap-x-3 gap-y-0.5 pt-0.5">
        <h3 className={cn('font-serif text-[1.0625rem] font-semibold', state === 'todo' && 'text-muted-foreground')}>{item.stage}阶段</h3>
        <PlanLine plan={plan} />
      </div>
      {(outputs.length > 0 || runningElsewhere || (state === 'current' && flow.waiting === 'assistant')) && (
        <ul className="-mx-3 mt-1.5 space-y-0.5">
          {runningElsewhere && <Pending tone="running" />}
          <Outputs outputs={outputs} pending={pending} names={names} onOpen={onOpen} />
          {state === 'current' && flow.waiting === 'assistant' && <Pending tone="next" />}
        </ul>
      )}
    </Rail>
  )
}

/** 阶段名旁的计划：「步骤 原码复现、复现性分析 · skill PDF 解析」；一样都没点名就不写 */
function PlanLine({ plan }: { plan: StagePlan }) {
  if (plan.steps.length === 0 && plan.skills.length === 0) return null
  return (
    <span className="flex flex-wrap gap-x-3 text-[0.8125rem] text-muted-foreground">
      {plan.steps.length > 0 && <span>步骤 <ChipNames chips={plan.steps} /></span>}
      {plan.skills.length > 0 && <span>skill <ChipNames chips={plan.skills} /></span>}
    </span>
  )
}

function ChipNames({ chips }: { chips: Chip[] }) {
  return chips.map((chip, i) => (
    <span key={chip.title}>{i > 0 && '、'}<span title={chip.brief || undefined} className="text-foreground/80">{chip.title}</span></span>
  ))
}

/** 一个阶段的产出：新的在前、露最近两次（待确认与运行中的总露着），其余「还有 N 次」点开 */
function Outputs({ outputs, pending, names, onOpen }: {
  outputs: OutputBrief[]; pending: Set<string>; names: Names; onOpen: (oid: string) => void
}) {
  const [open, setOpen] = useState(false)
  const { shown, hidden, failed } = fold(outputs, pending)
  const rows = open ? fold(outputs, pending, Infinity).shown : shown
  return (
    <>
      {rows.map((o) => <OutputRow key={o.id} output={o} state={stateOf(o, pending)} names={names} onOpen={() => onOpen(o.id)} />)}
      {hidden.length > 0 && (
        <li>
          <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[0.8125rem] text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring">
            {open ? <>收起<CaretUp className="size-3.5" aria-hidden /></> : (
              <>还有 {hidden.length} 次{failed > 0 && <span className="text-bad">（{failed} 次失败）</span>}<CaretDown className="size-3.5" aria-hidden /></>
            )}
          </button>
        </li>
      )}
    </>
  )
}

const STATE_WORD: Record<OutputState, string> = {
  running: '运行中', failed: '失败', pending: '待确认', confirmed: '已确认', done: '完成',
}

/** 一行产出：左「第 N 次」，中间产出名与一行事实（生成者 · 读取 · 时间与用时），右边状态；整行可点，跟着鼠标亮一团光；
 *  待确认那行垫琥珀软底——人要做的事一眼看见 */
function OutputRow({ output, state, names, onOpen }: {
  output: OutputBrief; state: OutputState; names: Names; onOpen: () => void
}) {
  const n = output.id.split('/')[1]
  const reads = output.from.map((id) => outputName(id, names.stage, names.workspace)).join('、')
  return (
    <li>
      <button type="button" onClick={onOpen} onMouseMove={follow}
              className={cn('group/out relative isolate grid w-full grid-cols-[3.5rem_minmax(0,1fr)_auto] items-start gap-x-3 rounded-xl px-3 py-2.5 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/60',
                            state === 'pending' && 'bg-wait-soft/70')}>
        <Spot group="out" size="20rem" />
        <span className={cn('pt-px text-[0.8125rem] whitespace-nowrap tabular', state === 'pending' ? 'text-wait' : 'text-muted-foreground')}>
          第 {n} 次
        </span>
        <span className="min-w-0">
          <span className={cn('block truncate text-[0.9375rem] leading-snug font-medium', state === 'failed' && 'text-foreground/70')}>{output.title}</span>
          <span className="mt-0.5 flex flex-wrap gap-x-3 text-[0.75rem] leading-relaxed text-muted-foreground">
            <Fact k="生成者">{byWord(output.by, names.cap)}</Fact>
            {reads && <Fact k="读取">{reads}</Fact>}
            <span className="whitespace-nowrap tabular">{when(output.created_at)}{output.finished_at && ` · 用时 ${tookWord(output.created_at, output.finished_at)}`}</span>
          </span>
        </span>
        <StateMark state={state} />
      </button>
    </li>
  )
}

/** 事实一格：浅色的键 + 深一点的值；窄了在格与格之间换行，不断在词中间 */
function Fact({ k, children }: { k: string; children: ReactNode }) {
  return <span>{k} <span className="text-foreground/75">{children}</span></span>
}

function StateMark({ state }: { state: OutputState }) {
  const word = STATE_WORD[state]
  const base = 'flex items-center gap-1.5 pt-px text-[0.8125rem] whitespace-nowrap'
  if (state === 'running') return <span className={cn(base, 'text-primary')}><Dot tone="primary" pulse />{word}</span>
  if (state === 'failed') return <span className={cn(base, 'text-bad')}><WarningCircle className="size-4" aria-hidden />{word}</span>
  if (state === 'pending') return <span className={cn(base, 'font-semibold text-wait')}><Signature weight="fill" className="size-4" aria-hidden />{word}</span>
  if (state === 'confirmed') return <span className={cn(base, 'text-ok')}><CheckCircle weight="fill" className="size-4" aria-hidden />{word}</span>
  return <span className={cn(base, 'text-muted-foreground')}>{word}</span>
}

/** 还没有产出的一行：作业起了、目录还没开（运行中）；流程正等助理开始这一格（下一步） */
function Pending({ tone }: { tone: 'running' | 'next' }) {
  return (
    <li className="flex items-center gap-2 px-3 py-2 text-[0.8125rem] text-primary">
      {tone === 'running' ? <><Dot tone="primary" pulse />运行中</> : <><ArrowRight className="size-4" aria-hidden />下一步 · 助理</>}
    </li>
  )
}

/** 一个断点：节点是一枚小菱形（已确认 铜绿 / 待确认 琥珀带一圈光 / 没到 描边），旁边「断点」+ 那句话，右边状态 */
function StopNode({ item, flow, last }: { item: Extract<FlowProgressItem, { kind: 'stop' }>; flow: FlowProgress; last: boolean }) {
  const state = stopState(item, flow)
  const note = item.note || '确认'
  return (
    <Rail line={last ? null : state === 'signed' ? 'solid' : 'dashed'}
          node={
            <span aria-hidden="true"
                  className={cn('size-2.5 rotate-45 rounded-[2px]',
                                state === 'signed' && 'bg-ok',
                                state === 'pending' && 'bg-wait shadow-[0_0_0_5px_color-mix(in_oklab,var(--wait)_20%,transparent)]',
                                state === 'todo' && 'border-[1.5px] border-foreground/30')} />
          }>
      <div className={cn('flex min-h-7 flex-wrap items-center gap-x-3 gap-y-0.5', state === 'todo' && 'text-muted-foreground')}>
        <span className="text-[0.875rem] font-medium">断点</span>
        <span className="min-w-0 flex-1 text-[0.875rem] text-foreground/80">{note}</span>
        {state === 'signed' && <span className="flex items-center gap-1.5 text-[0.8125rem] text-ok"><CheckCircle weight="fill" className="size-4" aria-hidden />已确认</span>}
        {state === 'pending' && <span className="flex items-center gap-1.5 text-[0.8125rem] font-semibold text-wait"><Signature weight="fill" className="size-4" aria-hidden />待确认</span>}
      </div>
    </Rail>
  )
}

/** 单独运行（主人 2026-10-06：「流程外的产出」看不懂）：没按流程、单独调用步骤跑出来的产出，标题悬停一句说清；
 *  次一级的面（只有玻璃），按阶段分组，组头是阶段图标 + 「X阶段」，行与流程里的一样 */
function Loose({ outputs, pending, names, onOpen }: {
  outputs: OutputBrief[]; pending: Set<string>; names: Names; onOpen: (oid: string) => void
}) {
  const groups = [...new Set(outputs.map((o) => o.stage))].map((slug) => ({ slug, outputs: outputs.filter((o) => o.stage === slug) }))
  return (
    <section aria-label="单独运行">
      <h2 className="flex w-fit cursor-help items-baseline gap-2 px-1" title="没按流程、单独调用步骤跑出来的产出">
        <span className="font-serif text-[1.0625rem] font-semibold">单独运行</span>
        <Info className="size-3.5 self-center text-muted-foreground" aria-hidden />
        <span className="text-[0.8125rem] text-muted-foreground tabular">{outputs.length}</span>
      </h2>
      <Aurora quiet className="mt-3">
        {groups.map((g) => {
          const stage = names.stage(g.slug)
          return (
            <div key={g.slug} className="px-6 pt-4 pb-3 not-first:border-t not-first:border-foreground/[0.06]">
              <h3 className="flex items-center gap-2 text-[0.875rem] font-medium text-foreground/85">
                {createElement(stageIcon(stage), { weight: 'duotone', 'aria-hidden': true, className: 'size-4 text-foreground/60' })}
                {stage}阶段
              </h3>
              <ul className="-mx-3 mt-1.5 space-y-0.5">
                <Outputs outputs={g.outputs} pending={pending} names={names} onOpen={onOpen} />
              </ul>
            </div>
          )
        })}
      </Aurora>
    </section>
  )
}

/** 停一个正在跑的作业：第一下只是拉开保险（变红），第二下才停（外层 #115）。 */
function StopKey({ workspace, jobId, onChanged }: { workspace: WorkspaceClient; jobId: string; onChanged: () => Promise<void> }) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const press = async () => {
    if (!armed) { setArmed(true); return }
    setBusy(true)
    setError(null)
    try {
      await workspace.stopJob(jobId)
      await onChanged()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
      setArmed(false)
    }
  }
  return (
    <span className="flex items-center gap-2">
      <button type="button" onClick={press} onBlur={() => setArmed(false)} disabled={busy}
              className={cn('rounded-full border px-3 py-1 text-[0.8125rem] transition-colors focus-visible:outline-2 focus-visible:outline-ring',
                            armed ? 'border-bad bg-bad/10 text-bad' : 'bg-card/70 text-muted-foreground hover:text-foreground')}>
        {busy ? '停止中' : armed ? '确认停止' : '停止'}
      </button>
      {error && <ErrorNote text={error} />}
    </span>
  )
}

/** 删这条流程实例（主人 2026-09-22）：一次产出都没挂、没在跑才出现；按住一秒才删 */
function RemoveFlowKey({ workspace, name, onChanged }: { workspace: WorkspaceClient; name: string; onChanged: () => Promise<void> }) {
  const [failed, setFailed] = useState<string | null>(null)
  const remove = () => {
    setFailed(null)
    workspace.removeFlow(name).then(() => onChanged()).catch((exc: unknown) => setFailed(exc instanceof Error ? exc.message : String(exc)))
  }
  return (
    <span className="flex items-center gap-2">
      <HoldButton onHold={remove} doneLabel="已删除"><Trash className="size-3.5" />删除</HoldButton>
      {failed && <span className="text-[0.75rem] text-bad">{failed}</span>}
    </span>
  )
}
