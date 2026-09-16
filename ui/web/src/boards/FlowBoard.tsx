import { Check, Plus, X } from 'lucide-react'
import { useEffect, useState } from 'react'

import { api } from '@/api/client'
import type { Capability } from '@/api/types'
import { ErrorNote, Pill, Problems, Section, Skeleton } from '@/components/bits'
import { Button } from '@/components/ui/button'
import { useResource } from '@/lib/useResource'

const LEVEL_LABEL: Record<Capability['level'], string> = {
  task: '任务包上的按钮', run: 'run 上的按钮', project: '项目级',
}
const LEVELS: Capability['level'][] = ['task', 'run', 'project']

export function FlowBoard() {
  const catalog = useResource(api.capabilities, [])
  const [steps, setSteps] = useState<string[]>([])
  const [problems, setProblems] = useState<string[] | null>(null)
  const [checkError, setCheckError] = useState<string | null>(null)

  // 步骤一变就问服务通不通；只是对吃吐文件，不跑任何东西。清空由改步骤的事件顺手做。
  useEffect(() => {
    if (steps.length === 0) return
    let cancelled = false
    api.flowCheck(steps)
      .then((found) => { if (!cancelled) { setProblems(found.problems); setCheckError(null) } })
      .catch((exc: unknown) => {
        if (!cancelled) setCheckError(exc instanceof Error ? exc.message : String(exc))
      })
    return () => { cancelled = true }
  }, [steps])

  const change = (next: string[]) => {
    setSteps(next)
    setProblems(null)
  }

  const byLevel = groupBy(catalog.data ?? [], (c) => c.level)

  return (
    <div className="space-y-5 p-4">
      <p className="text-sm leading-relaxed text-muted-foreground">
        这些是助理能按的按钮，每颗吃几个文件、吐几个文件。把它们排成一串就是一条流；
        这里只检查通不通，真正跑还是助理在对话里一颗一颗按。
      </p>

      <Section title="这条流"
               aside={steps.length > 0 && problems !== null && (
                 <Pill tone={problems.length === 0 ? 'ok' : 'bad'}>
                   {problems.length === 0 ? <><Check className="size-3" />通</> : '不通'}
                 </Pill>
               )}>
        {steps.length === 0 ? (
          <p className="rounded-lg border border-dashed px-3 py-3 text-sm text-muted-foreground">
            从下面挑按钮，按顺序加进来。
          </p>
        ) : (
          <ol className="flex flex-wrap items-center gap-1.5">
            {steps.map((name, i) => (
              <li key={`${name}-${i}`} className="flex items-center gap-1.5">
                <span className="inline-flex items-center gap-1 rounded-md border bg-background py-1 pr-1 pl-2.5 font-mono text-xs">
                  {name}
                  <button type="button" aria-label={`移除 ${name}`}
                          onClick={() => change(steps.filter((_, j) => j !== i))}
                          className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground">
                    <X className="size-3" />
                  </button>
                </span>
                {i < steps.length - 1 && <span className="text-muted-foreground">→</span>}
              </li>
            ))}
          </ol>
        )}
        {checkError && <ErrorNote text={checkError} />}
        {problems && <Problems items={problems} />}
      </Section>

      {catalog.error && <ErrorNote text={catalog.error} />}
      {catalog.loading && !catalog.data && <Skeleton lines={5} />}
      {LEVELS.map((level) => byLevel[level]?.length ? (
        <Section key={level} title={LEVEL_LABEL[level]}>
          <ul className="divide-y rounded-lg border">
            {byLevel[level].map((cap) => (
              <li key={cap.name} className="flex items-start gap-3 px-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-medium">{cap.name}</span>
                    {cap.needs_executor && <Pill tone="neutral">要执行层</Pill>}
                  </div>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{cap.summary}</p>
                  <Files label="吃" files={cap.inputs.map((f) => f.path)} />
                  <Files label="吐" files={cap.outputs.map((f) => f.path)} />
                </div>
                <Button variant="outline" size="xs" onClick={() => change([...steps, cap.name])}
                        aria-label={`把 ${cap.name} 加进这条流`}>
                  <Plus data-icon="inline-start" />加入
                </Button>
              </li>
            ))}
          </ul>
        </Section>
      ) : null)}
    </div>
  )
}

function Files({ label, files }: { label: string; files: string[] }) {
  if (files.length === 0) return null
  return (
    <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
      <span className="mr-1">{label}</span>
      {files.map((f) => <code key={f} className="mr-1.5 rounded bg-muted px-1 font-mono">{f}</code>)}
    </p>
  )
}

function groupBy<T, K extends string>(items: T[], key: (item: T) => K): Record<K, T[]> {
  return items.reduce((acc, item) => {
    (acc[key(item)] ??= []).push(item)
    return acc
  }, {} as Record<K, T[]>)
}
