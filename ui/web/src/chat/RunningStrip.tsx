// 对话输入框上方的「运行中 N」（外层 #243）：项目里有作业在跑就出现，没有就不占地方。长任务交给后台以后对话里会安静很久，
// 这一条告诉人东西一直在跑：一颗靛点一圈一圈往外扩（与设置板上「就绪」的心跳同一种动），点开是每个作业一行——能力的名、
// 在哪个工作区（项目里不止一个时）、已运行多久；点一行去看那次产出的进度面板。停止仍在看板上，这里不重复放。
import { CaretRight, CaretUp } from '@phosphor-icons/react'
import { useState } from 'react'

import { Clock } from '@/components/Clock'
import { cn } from '@/lib/utils'

import type { RunningJob } from './running'

export function RunningStrip({ jobs, titleOf, showWorkspace, onOpen }: {
  jobs: RunningJob[]
  /** 能力名 → 页面上的名（描述符的 title） */
  titleOf: (cap: string) => string
  /** 项目里不止一个工作区：每行带上工作区的名 */
  showWorkspace: boolean
  /** 去看这个作业那次产出的进度；作业还没开出产出时这一行点不了 */
  onOpen: (job: RunningJob) => void
}) {
  const [open, setOpen] = useState(false)
  if (jobs.length === 0) return null
  return (
    <div className="mx-auto mb-2 w-full max-w-[44rem]">
      <div className={cn('inline-flex max-w-full flex-col rounded-2xl bg-card/85 ring-1 ring-foreground/[0.07] backdrop-blur-sm transition-[width] duration-200',
                         open ? 'w-[22rem] shadow-[0_8px_28px_-18px_rgb(0_0_0/0.35)]' : 'w-auto')}>
        {open && (
          <ul className="space-y-0.5 px-1.5 pt-1.5">
            {jobs.map((job) => (
              <li key={job.job_id}>
                <button type="button" disabled={!job.output} onClick={() => onOpen(job)}
                        className="group flex w-full items-center gap-3 rounded-xl px-2.5 py-2 text-left text-[0.8125rem] transition-colors enabled:hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-default">
                  <span className="min-w-0 flex-1 truncate">
                    {titleOf(job.cap)}
                    {showWorkspace && <span className="ml-2 text-muted-foreground">{job.workspaceTitle}</span>}
                  </span>
                  <Clock since={job.started_at} className="text-[0.75rem] text-muted-foreground" />
                  <CaretRight className={cn('size-3.5 text-muted-foreground transition-colors group-enabled:group-hover:text-primary', !job.output && 'invisible')} />
                </button>
              </li>
            ))}
          </ul>
        )}
        <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
                className="flex items-center gap-2 rounded-2xl px-3.5 py-2 text-[0.8125rem] text-primary focus-visible:outline-2 focus-visible:outline-ring">
          <span className="relative grid size-2 place-items-center" aria-hidden>
            <span className="absolute inset-0 rounded-full bg-primary animate-pulse-ring" />
            <span className="size-2 rounded-full bg-primary" />
          </span>
          运行中 {jobs.length}
          <CaretUp weight="bold" className={cn('ml-auto size-3 transition-transform duration-200', open && 'rotate-180')} />
        </button>
      </div>
    </div>
  )
}
