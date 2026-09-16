// 进度页：每个课题走到哪了。五步固定：接任务 → 跑基线 → 做实验 → 写分析 → 验证；
// 状态从任务包与 run 的真实文件推出来，不是页面自己的记忆。

import { Check } from 'lucide-react'

import { api } from '@/api/client'
import { Empty, ErrorNote, Skeleton } from '@/components/bits'
import { Button } from '@/components/ui/button'
import { progressOf, STEPS, type StepState } from '@/lib/progress'
import { useResource } from '@/lib/useResource'
import { cn } from '@/lib/utils'

interface Props {
  epoch: number
  onOpenTask: (id: string) => void
  onOpenRun: (id: string) => void
}

export function ProgressBoard({ epoch, onOpenTask, onOpenRun }: Props) {
  const tasks = useResource(api.tasks, [epoch])
  const runs = useResource(api.runs, [epoch])
  const loading = (tasks.loading && !tasks.data) || (runs.loading && !runs.data)
  return (
    <div className="space-y-8 px-6 py-4">
      {tasks.error && <ErrorNote text={tasks.error} />}
      {runs.error && <ErrorNote text={runs.error} />}
      {loading && <Skeleton lines={5} />}
      {tasks.data?.length === 0 && <Empty title="还没有课题。" hint="先在对话里说清想做什么。" />}
      {tasks.data && runs.data && tasks.data.map((task) => {
        const p = progressOf(task, runs.data!)
        return (
          <section key={task.id} className="space-y-4">
            <h3 className="text-[0.9375rem] font-semibold tracking-tight">{task.title}</h3>
            <Stepper states={p.states} />
            <div className="t-body space-y-1">
              <p>{p.now}</p>
              <p className="text-muted-foreground">{p.next}</p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => onOpenTask(task.id)}>看需求</Button>
              {p.run && <Button variant="outline" size="sm" onClick={() => onOpenRun(p.run!.run_id)}>看结果</Button>}
            </div>
          </section>
        )
      })}
    </div>
  )
}

/** 被动的五步进度：做完打勾、当前实心、未到空心。 */
function Stepper({ states }: { states: StepState[] }) {
  return (
    <ol className="grid grid-cols-5" aria-label="进度">
      {STEPS.map((label, i) => {
        const state = states[i]
        const last = i === STEPS.length - 1
        return (
          <li key={label} className="relative flex flex-col items-center gap-2">
            {!last && (
              <span className={cn('absolute top-3 left-1/2 h-px w-full', state === 'done' ? 'bg-primary' : 'bg-border')} aria-hidden />
            )}
            <span className={cn('relative z-10 flex size-6 items-center justify-center rounded-full border text-[11px] font-semibold transition-colors duration-200',
                                state === 'done' && 'border-primary bg-primary text-primary-foreground',
                                state === 'current' && 'border-primary bg-background text-primary ring-3 ring-primary/20',
                                state === 'todo' && 'border-border bg-background text-muted-foreground')}>
              {state === 'done' ? <Check className="size-3.5" aria-label="已完成" /> : i + 1}
            </span>
            <span className={cn('text-xs', state === 'current' ? 'font-medium text-foreground' : 'text-muted-foreground')}>{label}</span>
          </li>
        )
      })}
    </ol>
  )
}
