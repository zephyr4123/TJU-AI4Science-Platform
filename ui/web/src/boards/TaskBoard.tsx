// 需求页：助理写给你的一页纸——这份需求是什么、怎么算好、花多少，看完署名发布。

import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'

import { api } from '@/api/client'
import type { TaskDetail, TaskSummary } from '@/api/types'
import ClickSpark from '@/components/ClickSpark'
import {
  BigNumber, Details, DoneBlock, Dot, Empty, ErrorNote, KeyBlock, Lede, Numbers, Paragraph, Problems,
  Skeleton, type Tone,
} from '@/components/bits'
import { Markdown } from '@/components/Markdown'
import { Button } from '@/components/ui/button'
import { metric, when } from '@/lib/format'
import {
  budgetNumbers, budgetSentence, gateSentence, goalSentence, STAGE_LABEL, STAGE_NEXT,
} from '@/lib/humanize'
import { useResource } from '@/lib/useResource'
import { useSigner } from '@/lib/useSigner'

import { SignerField } from './SignerField'

const STAGE_TONE: Record<TaskSummary['stage'], Tone> = {
  drafting: 'neutral', published: 'primary', designed: 'warn', baselined: 'ok',
}

interface Props {
  epoch: number
  selected: string | null
  onSelect: (id: string | null) => void
}

export function TaskBoard({ epoch, selected, onSelect }: Props) {
  const list = useResource(api.tasks, [epoch])
  if (selected) {
    return <TaskPage id={selected} epoch={epoch} onBack={() => onSelect(null)} onChanged={list.reload} />
  }
  return (
    <div className="space-y-5 px-6 py-4">
      {list.error && <ErrorNote text={list.error} />}
      {list.loading && !list.data && <Skeleton lines={4} />}
      {list.data?.length === 0 && (
        <Empty title="还没有需求。" hint="在对话里说清课题，助理会整理成一份需求放到这里。" />
      )}
      {list.data && list.data.length > 0 && (
        <>
          <p className="t-body text-muted-foreground">每份需求助理起草、你发布。没发布的，后面的按钮都不开。</p>
          <ul className="divide-y">
            {list.data.map((task) => (
              <li key={task.id}>
                <button type="button" onClick={() => onSelect(task.id)}
                        className="-mx-2 flex w-full items-start gap-3 rounded-md px-2 py-3.5 text-left transition-colors duration-150 hover:bg-muted/60">
                  <Dot tone={STAGE_TONE[task.stage]} className="mt-2" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[0.9375rem] font-medium">{task.title}</span>
                    <span className="t-label mt-0.5 block">{STAGE_LABEL[task.stage]}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

function TaskPage({ id, epoch, onBack, onChanged }: {
  id: string; epoch: number; onBack: () => void; onChanged: () => Promise<void>
}) {
  const task = useResource(() => api.task(id), [id, epoch])
  return (
    <div className="px-6 py-4">
      <Button variant="ghost" size="sm" onClick={onBack} className="-ml-2 mb-4">
        <ArrowLeft data-icon="inline-start" />全部需求
      </Button>
      {task.error && <ErrorNote text={task.error} />}
      {task.loading && !task.data && <Skeleton lines={6} />}
      {task.data && <TaskSheet task={task.data} reload={async () => { await task.reload(); await onChanged() }} />}
    </div>
  )
}

function TaskSheet({ task, reload }: { task: TaskDetail; reload: () => Promise<void> }) {
  const budget = (task.manifest.budget ?? {}) as Record<string, unknown>
  const requirements = (task.manifest.requirements ?? []) as { id: string; description: string }[]
  const headroom = task.headroom
  const numbers = budgetNumbers(budget)
  return (
    <article className="space-y-8">
      <header className="space-y-3">
        <h2 className="t-label">{task.id}</h2>
        <Lede tone={task.publish.ok ? 'ok' : 'neutral'}>
          {task.publish.ok ? `已发布。${STAGE_LABEL[task.stage]}。` : '这份需求还没发布。'}
        </Lede>
        <p className="t-body text-muted-foreground">{STAGE_NEXT[task.stage]}</p>
      </header>

      <Numbers>
        {numbers.map((n) => <BigNumber key={n.label} label={n.label} value={n.value} unit={n.unit} missing="不限" />)}
      </Numbers>

      <div className="space-y-6">
        <Paragraph title="想解决什么">
          <p className="font-medium">{task.title}</p>
          {task.question && <p className="mt-1">{task.question}</p>}
        </Paragraph>
        <Paragraph title="怎么算好">
          <p>{goalSentence(task, headroom?.baseline)}</p>
          {headroom && headroom.problems.length === 0 && (
            <p className="mt-1">{gateSentence(headroom.sigma, headroom.gate, headroom.gates)}</p>
          )}
          {headroom && headroom.problems.length > 0 && (
            <div className="mt-2"><Problems items={headroom.problems} /></div>
          )}
        </Paragraph>
        <Paragraph title="花多少">
          <p>{budgetSentence(budget)}</p>
        </Paragraph>
        {requirements.length > 0 && (
          <Paragraph title="什么样的结果才算数">
            <ul className="list-disc space-y-1 pl-5">
              {requirements.map((req) => <li key={req.id}>{req.description}</li>)}
            </ul>
          </Paragraph>
        )}
      </div>

      <PublishKey task={task} reload={reload} />

      <div className="space-y-3">
        <Details title="助理写的设计说明">
          {task.design ? <Markdown text={task.design} /> : <p className="t-body text-muted-foreground">还没写。发布前它要说清产物契约与「怎么算好」。</p>}
        </Details>
        <Details title="技术细节">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-muted-foreground">领域包</dt><dd className="font-mono">{task.domain}</dd>
            {task.metric && <><dt className="text-muted-foreground">主指标</dt><dd className="font-mono">{task.metric.name} · {task.metric.direction}{task.metric.attainable != null ? ` · attainable ${metric(task.metric.attainable)}` : ''}</dd></>}
            {Object.entries(budget).map(([key, value]) => (
              <span key={key} className="contents"><dt className="text-muted-foreground">budget.{key}</dt><dd className="font-mono">{String(value)}</dd></span>
            ))}
            {headroom?.summary && <><dt className="text-muted-foreground">预检</dt><dd className="font-mono whitespace-pre-wrap break-all">{headroom.summary}</dd></>}
          </dl>
        </Details>
      </div>
    </article>
  )
}

function PublishKey({ task, reload }: { task: TaskDetail; reload: () => Promise<void> }) {
  const [signer, setSigner] = useSigner()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  if (task.publish.ok) {
    return (
      <DoneBlock title={`${task.publish.by} 已发布`}
                 detail={<>{when(task.publish.at)}。改了需求或设计说明就要重新发布。</>} />
    )
  }
  const blocked = task.intake_problems.length > 0
  return (
    <KeyBlock
      title="发布这份需求"
      hint={task.publish.state === 'invalid' && task.publish.reason
        ? task.publish.reason
        : '上面几段就是助理要照着做的事。确认这就是你要的，署名发布；之后它才能接任务。这颗键只有人能按。'}
    >
      {blocked && <div className="mb-3"><Problems items={task.intake_problems} tone="warn" /></div>}
      {error && <div className="mb-3"><ErrorNote text={error} /></div>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SignerField id="publish-signer" value={signer} onChange={setSigner} />
        <ClickSpark sparkColor="oklch(0.62 0.15 72)" sparkRadius={20} sparkCount={8} duration={420}>
          <Button size="lg" onClick={press} disabled={busy || blocked || !signer.trim()}>
            {busy ? '发布中…' : '发布需求'}
          </Button>
        </ClickSpark>
      </div>
    </KeyBlock>
  )
}
