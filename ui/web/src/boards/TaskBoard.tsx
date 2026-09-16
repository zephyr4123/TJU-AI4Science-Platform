import { ArrowLeft, Check, ChevronDown, KeyRound } from 'lucide-react'
import { useState } from 'react'

import { api } from '@/api/client'
import type { Headroom, Stage, TaskDetail, TaskSummary } from '@/api/types'
import ClickSpark from '@/components/ClickSpark'
import { Dot, Empty, ErrorNote, Pill, Problems, Row, Section, Skeleton, type Tone } from '@/components/bits'
import { Markdown } from '@/components/Markdown'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { metric, when } from '@/lib/format'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

import { useSigner } from '@/lib/useSigner'

import { SignerField } from './SignerField'

const STAGE: Record<Stage, { label: string; tone: Tone; next: string }> = {
  drafting: { label: '需求未发布', tone: 'neutral', next: '看过 manifest 与设计说明后按「发布」' },
  published: { label: '已发布', tone: 'primary', next: '让助理接任务：写裁判脚本与基线草稿' },
  designed: { label: '已接任务', tone: 'warn', next: '让助理跑基线，机器会预检有没有改进空间' },
  baselined: { label: '可开跑', tone: 'ok', next: '让助理开实验；结果在「结果」看板验收' },
}
const STAGE_ORDER: Stage[] = ['drafting', 'published', 'designed', 'baselined']

interface Props {
  epoch: number
  selected: string | null
  onSelect: (id: string | null) => void
}

export function TaskBoard({ epoch, selected, onSelect }: Props) {
  const list = useResource(api.tasks, [epoch])
  if (selected) {
    return <TaskDetailView id={selected} epoch={epoch} onBack={() => onSelect(null)}
                           onChanged={list.reload} />
  }
  return (
    <div className="space-y-3 p-4">
      <p className="text-sm leading-relaxed text-muted-foreground">
        每个任务包是一份需求：问题、指标、预算、怎么算好。助理起草，你看过再发布；没发布的需求，
        后面的按钮都不开。
      </p>
      {list.error && <ErrorNote text={list.error} />}
      {list.loading && !list.data && <Skeleton lines={4} />}
      {list.data?.length === 0 && (
        <Empty title="还没有任务包" hint="在对话里描述你的课题，助理会建一个。" />
      )}
      <ul className="divide-y rounded-lg border">
        {list.data?.map((task) => <TaskRow key={task.id} task={task}
                                          onOpen={() => onSelect(task.id)} />)}
      </ul>
    </div>
  )
}

function TaskRow({ task, onOpen }: { task: TaskSummary; onOpen: () => void }) {
  const stage = STAGE[task.stage]
  return (
    <li>
      <button type="button" onClick={onOpen}
              className="flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors duration-150 hover:bg-muted/60">
        <Dot tone={stage.tone} className="mt-1.5" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{task.title}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
            <span className="font-mono">{task.id}</span>
            <span>·</span>
            <span>{stage.label}</span>
            {task.metric && (
              <><span>·</span><span className="font-mono">{task.metric.name} {task.metric.direction === 'minimize' ? '↓' : '↑'}</span></>
            )}
          </div>
        </div>
      </button>
    </li>
  )
}

function TaskDetailView({ id, epoch, onBack, onChanged }: {
  id: string; epoch: number; onBack: () => void; onChanged: () => Promise<void>
}) {
  const task = useResource(() => api.task(id), [id, epoch])
  return (
    <div className="space-y-5 p-4">
      <Button variant="ghost" size="sm" onClick={onBack} className="-ml-2">
        <ArrowLeft data-icon="inline-start" />全部任务
      </Button>
      {task.error && <ErrorNote text={task.error} />}
      {task.loading && !task.data && <Skeleton lines={6} />}
      {task.data && (
        <TaskBody task={task.data} reload={async () => { await task.reload(); await onChanged() }} />
      )}
    </div>
  )
}

function TaskBody({ task, reload }: { task: TaskDetail; reload: () => Promise<void> }) {
  const budget = (task.manifest.budget ?? {}) as Record<string, unknown>
  const requirements = (task.manifest.requirements ?? []) as
    { id: string; description: string; must_pass?: boolean }[]
  return (
    <>
      <header>
        <h2 className="text-base font-semibold tracking-tight">{task.title}</h2>
        <p className="mt-0.5 font-mono text-xs text-muted-foreground">{task.id} · {task.domain}</p>
      </header>

      <StageTrack stage={task.stage} />

      <PublishPanel task={task} reload={reload} />

      {task.question && (
        <Section title="研究问题">
          <p className="max-w-prose text-sm leading-relaxed">{task.question}</p>
        </Section>
      )}

      <Section title="指标与预算">
        <dl className="divide-y rounded-lg border px-3">
          {task.metric && (
            <Row label="主指标">
              {task.metric.name}{' '}
              <span className="text-muted-foreground">{task.metric.direction === 'minimize' ? '越小越好' : '越大越好'}</span>
            </Row>
          )}
          {task.metric?.attainable != null && <Row label="尽头值">{metric(task.metric.attainable)}</Row>}
          {Object.entries(budget).map(([key, value]) => (
            <Row key={key} label={BUDGET_LABEL[key] ?? key}>{String(value)}</Row>
          ))}
        </dl>
      </Section>

      {task.headroom && <HeadroomPanel found={task.headroom} />}

      {requirements.length > 0 && (
        <Section title="验收要求">
          <ul className="space-y-1.5">
            {requirements.map((req) => (
              <li key={req.id} className="flex gap-2 text-sm leading-relaxed">
                <span className="shrink-0 font-mono text-xs text-muted-foreground pt-0.5">{req.id}</span>
                <span>{req.description}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Collapsible defaultOpen={task.stage === 'drafting'}>
        <CollapsibleTrigger className="group flex w-full items-center justify-between py-1 text-[13px] font-semibold tracking-tight">
          设计说明（design.md）
          <ChevronDown className="size-4 text-muted-foreground transition-transform duration-150 group-data-[state=open]:rotate-180" />
        </CollapsibleTrigger>
        <CollapsibleContent>
          {task.design ? (
            <Markdown text={task.design} className="mt-2 rounded-lg border px-4 py-3" />
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">还没写。发布前它必须说清产物契约与「怎么算好」。</p>
          )}
        </CollapsibleContent>
      </Collapsible>
    </>
  )
}

const BUDGET_LABEL: Record<string, string> = {
  wall_clock_s: '单次墙钟上限（秒）', max_iterations: '总轮数上限', inner_k: '评分内部重复次数',
  repeat_k: '估 σ 的重复次数', accept_sigma: '统计门（σ 的倍数）', min_delta: '最小改进',
  max_cost_usd: '花费上限（美元）', patience: '连续不改进几轮就停',
}

function StageTrack({ stage }: { stage: Stage }) {
  const at = STAGE_ORDER.indexOf(stage)
  return (
    <ol className="flex items-center gap-1" aria-label="任务阶段">
      {STAGE_ORDER.map((s, i) => (
        <li key={s} className="flex flex-1 flex-col gap-1.5">
          <span className={cn('h-1 rounded-full transition-colors duration-200',
                              i <= at ? 'bg-primary' : 'bg-muted')} />
          <span className={cn('text-[11px] leading-tight',
                              i === at ? 'font-medium text-foreground' : 'text-muted-foreground')}>
            {STAGE[s].label}
          </span>
        </li>
      ))}
    </ol>
  )
}

function PublishPanel({ task, reload }: { task: TaskDetail; reload: () => Promise<void> }) {
  const [signer, setSigner] = useSigner()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const publish = task.publish

  const press = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.publish(task.id, signer)
      await reload()
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc))
    } finally {
      setBusy(false)
    }
  }

  if (publish.ok) {
    return (
      <div className="flex items-start gap-2 rounded-lg bg-ok-soft px-3 py-2.5 text-sm text-ok">
        <Check className="mt-0.5 size-4 shrink-0" />
        <div>
          <div className="font-medium">已发布</div>
          <div className="mt-0.5 text-xs opacity-80">{publish.by} · {when(publish.at)}。改了 manifest 或设计说明就要重新发布。</div>
          <p className="mt-1 text-xs opacity-80">下一步：{STAGE[task.stage].next}</p>
        </div>
      </div>
    )
  }

  const blocked = task.intake_problems.length > 0
  return (
    <div className="space-y-3 rounded-lg border border-primary/30 bg-accent/40 p-3">
      <div className="flex items-start gap-2">
        <KeyRound className="mt-0.5 size-4 shrink-0 text-primary" />
        <div className="text-sm leading-relaxed">
          <div className="font-medium">这颗键只有人能按</div>
          <p className="text-muted-foreground">
            {publish.state === 'invalid' && publish.reason
              ? publish.reason
              : '看过研究问题、指标、预算和设计说明，确认这就是你要的，再发布。发布之后助理才能接任务。'}
          </p>
        </div>
      </div>
      {blocked && <Problems items={task.intake_problems} tone="warn" />}
      {error && <ErrorNote text={error} />}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SignerField id="publish-signer" value={signer} onChange={setSigner} />
        <ClickSpark sparkColor="oklch(0.62 0.15 72)" sparkRadius={18} sparkCount={8} duration={420}>
          <Button onClick={press} disabled={busy || blocked || !signer.trim()}>
            {busy ? '发布中…' : '发布需求'}
          </Button>
        </ClickSpark>
      </div>
    </div>
  )
}

function HeadroomPanel({ found }: { found: Headroom }) {
  const bad = found.problems.length > 0
  return (
    <Section title="预检：有没有改进空间"
             aside={<Pill tone={bad ? 'bad' : 'ok'}>{bad ? '过不了' : '通过'}</Pill>}>
      {found.summary && (
        <dl className="divide-y rounded-lg border px-3">
          <Row label="基线">{metric(found.baseline)}</Row>
          <Row label="σ（重复跑）">{metric(found.sigma)}</Row>
          <Row label="统计门">{metric(found.gate)}</Row>
          <Row label="尽头值">{found.attainable == null ? '没填' : metric(found.attainable)}</Row>
          <Row label="到尽头的距离">
            {found.room == null ? '—' : `${metric(found.room)}（${found.gates === null || found.gates === undefined ? '—' : Number.isFinite(found.gates) ? `${found.gates.toFixed(1)} 个门` : '∞ 个门'}）`}
          </Row>
        </dl>
      )}
      <Problems items={found.problems} />
    </Section>
  )
}
