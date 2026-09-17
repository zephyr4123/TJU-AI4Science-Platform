// 工作流页：平台是一盒能力，能力各归一个科研阶段，工作流是预装的拼法。三张清单都从后端读，页面不写死顺序。

import { api } from '@/api/client'
import type { Capability, Workflow, WorkflowStep } from '@/api/types'
import { Empty, ErrorNote, Problems, Skeleton } from '@/components/bits'
import { LEVEL_COPY } from '@/lib/humanize'
import { actorOf, coverageSentence, groupByStage } from '@/lib/stages'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

export function WorkflowBoard() {
  const stages = useResource(api.stages, [])
  const workflows = useResource(api.workflows, [])
  const catalog = useResource(api.capabilities, [])
  const loading = [stages, workflows, catalog].some((r) => r.loading && !r.data)
  // 能力名 → 人话标题，步骤行与「用在哪几条流」都靠它翻译
  const titles = new Map<string, string>()
  for (const cap of catalog.data ?? []) titles.set(cap.name, cap.title)
  const workflowTitles = new Map<string, string>()
  for (const wf of workflows.data ?? []) workflowTitles.set(wf.name, wf.title)

  return (
    <div className="space-y-10 px-6 py-4">
      <p className="t-body text-muted-foreground">
        平台是一盒能力。每颗能力属于做科研的某一个阶段；工作流是预装好的拼法，助理可以照着走，也可以在对话里自己拼。
      </p>
      {stages.error && <ErrorNote text={stages.error} />}
      {workflows.error && <ErrorNote text={workflows.error} />}
      {catalog.error && <ErrorNote text={catalog.error} />}
      {loading && <Skeleton lines={6} />}

      {workflows.data && (
        <section className="space-y-6">
          <h2 className="t-lede">现在有 {workflows.data.length} 条工作流</h2>
          {workflows.data.length === 0 && <Empty title="还没有工作流。" hint="workflows/ 目录里一个文件一条。" />}
          {workflows.data.map((wf) => <WorkflowCard key={wf.name} workflow={wf} titles={titles} />)}
        </section>
      )}

      {catalog.data && stages.data && (
        <section className="space-y-5">
          <h2 className="t-lede">现在有 {catalog.data.length} 颗能力，分在 {stages.data.length} 个阶段里</h2>
          <p className="t-body text-muted-foreground">
            阶段只说这颗能力是干哪一段科研的，不定先后。每颗能力吃几个文件、吐几个文件，只认文件不认彼此。
            标「助理」的由执行层 agent 来做，标「机器」的不经过模型。
          </p>
          <ol className="space-y-5">
            {groupByStage(stages.data, catalog.data).map(({ stage, caps }) => (
              <li key={stage}>
                <h3 className="t-label mb-1">{stage}</h3>
                {caps.length === 0
                  ? <p className="py-2 text-sm text-muted-foreground">还没有这一步的能力。</p>
                  : (
                    <ul className="divide-y">
                      {caps.map((cap) => <CapabilityRow key={cap.name} cap={cap} workflowTitles={workflowTitles} />)}
                    </ul>
                  )}
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  )
}

function WorkflowCard({ workflow, titles }: { workflow: Workflow; titles: Map<string, string> }) {
  return (
    <article className="space-y-3">
      <div>
        <h3 className="text-[0.9375rem] font-semibold tracking-tight">
          {workflow.title}
          <span className="ml-2 font-mono text-xs font-normal text-muted-foreground">{workflow.name}</span>
        </h3>
        <p className="t-body mt-1 text-foreground/90">{workflow.summary}</p>
        <p className="t-label mt-1.5">{coverageSentence(workflow.covers)}</p>
      </div>
      <ol className="space-y-2">
        {workflow.steps.map((step, i) => <StepRow key={i} index={i + 1} step={step} titles={titles} />)}
      </ol>
      {workflow.remarks.map((remark) => (
        <p key={remark} className="text-sm text-warn">{remark}</p>
      ))}
      <Problems items={workflow.problems} />
    </article>
  )
}

/** 一步一行：谁做、做什么；是能力就带人话标题，是键就标出来。 */
function StepRow({ index, step, titles }: { index: number; step: WorkflowStep; titles: Map<string, string> }) {
  const human = step.by === '人'
  return (
    <li className="flex gap-3 text-[0.9375rem] leading-relaxed">
      <span className="w-5 shrink-0 text-right font-mono text-xs leading-6 text-muted-foreground tabular">{index}</span>
      <div className="min-w-0 flex-1">
        <span className={cn('mr-1.5 rounded px-1.5 py-0.5 text-xs font-medium',
                            human ? 'bg-accent text-accent-foreground' : 'bg-muted text-muted-foreground')}>
          {step.by}
        </span>
        <span>{step.does}</span>
        {step.cap && (
          <span className="ml-1.5 font-mono text-xs text-muted-foreground">能力 {titles.get(step.cap) ?? step.cap}</span>
        )}
        {step.key && (
          <span className="ml-1.5 font-mono text-xs text-primary">{step.key === 'publish' ? '发布键' : '验收键'}</span>
        )}
      </div>
    </li>
  )
}

function CapabilityRow({ cap, workflowTitles }: { cap: Capability; workflowTitles: Map<string, string> }) {
  const usedIn = cap.used_by.map((name) => workflowTitles.get(name) ?? name)
  return (
    <li className="py-3.5">
      <div className="flex items-baseline gap-2">
        <span className="text-[0.9375rem] font-medium">{cap.title}</span>
        <span className="font-mono text-xs text-muted-foreground">{cap.name}</span>
        <span className="ml-auto shrink-0 text-xs text-muted-foreground">
          {actorOf(cap)} · {LEVEL_COPY[cap.level]}
        </span>
      </div>
      <p className="t-body mt-1 text-foreground/90">{cap.what}</p>
      <p className="t-label mt-1.5">
        吃 {cap.inputs.map((f) => f.path).join('、')}；吐 {cap.outputs.map((f) => f.path).join('、')}
        {usedIn.length > 0 && <>；用在「{usedIn.join('」「')}」</>}
      </p>
    </li>
  )
}
