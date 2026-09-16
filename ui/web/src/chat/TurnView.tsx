import { ChevronRight, FileText, Search, ShieldBan, Terminal, Wrench } from 'lucide-react'

import { ErrorNote } from '@/components/bits'
import { Markdown } from '@/components/Markdown'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { seconds, usd } from '@/lib/format'
import { cn } from '@/lib/utils'

import { describeTool, type TraceItem, type TurnOutcome } from './trace'

export interface Turn {
  n: number
  message: string
  reply: string | null
  trace: TraceItem[]
  outcome: TurnOutcome | null
  live: boolean
}

export function TurnView({ turn }: { turn: Turn }) {
  const hasReply = turn.reply !== null && turn.reply !== ''
  // 回答已经落盘的轮次，trace 里的最后一段文本就是回答本身，不重复显示
  const trace = hasReply && !turn.live ? withoutTrailingText(turn.trace) : turn.trace
  return (
    <article className="space-y-3" aria-label={`第 ${turn.n} 轮`}>
      <div className="flex justify-end">
        <p className="max-w-[75%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-sm leading-relaxed">
          {turn.message}
        </p>
      </div>
      {(trace.length > 0 || turn.live) && (
        <ol className="space-y-1">
          {trace.map((item, i) => <TraceRow key={i} item={item} />)}
          {turn.live && <Thinking />}
        </ol>
      )}
      {hasReply && <Markdown text={turn.reply!} className="max-w-[72ch]" />}
      {turn.outcome && (
        <p className="text-xs text-muted-foreground tabular">
          {turn.outcome.failed ? '这一轮没走完' : '这一轮'}
          {' · '}{usd(turn.outcome.costUsd)}{' · '}{seconds(turn.outcome.durationS)}
        </p>
      )}
    </article>
  )
}

function withoutTrailingText(items: TraceItem[]): TraceItem[] {
  const last = items[items.length - 1]
  return last && last.kind === 'text' ? items.slice(0, -1) : items
}

function Thinking() {
  return (
    <li className="flex items-center gap-2 px-1 py-1 text-xs text-muted-foreground">
      <span className="relative flex size-2">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/60" />
        <span className="relative inline-flex size-2 rounded-full bg-primary" />
      </span>
      助理在想…
    </li>
  )
}

function TraceRow({ item }: { item: TraceItem }) {
  if (item.kind === 'error') return <li><ErrorNote text={item.text} /></li>
  if (item.kind === 'text') {
    return (
      <li className="px-1 py-1">
        <Markdown text={item.text} className="max-w-[72ch] text-muted-foreground" />
      </li>
    )
  }
  const pending = item.result === null
  return (
    <li>
      <Collapsible>
        <CollapsibleTrigger
          className={cn('group flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-xs',
                        'hover:bg-muted transition-colors duration-150',
                        item.denied && 'text-bad', item.isError && !item.denied && 'text-warn')}
        >
          <ChevronRight className="size-3.5 shrink-0 text-muted-foreground transition-transform duration-150 group-data-[state=open]:rotate-90" />
          <ToolIcon tool={item.tool} denied={item.denied} />
          <code className="min-w-0 flex-1 truncate font-mono text-[12px]">
            {describeTool(item.tool, item.input)}
          </code>
          <span className="shrink-0 text-muted-foreground">
            {item.denied ? '被拒绝' : pending ? '运行中…' : item.isError ? '出错' : '完成'}
          </span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <pre className="mt-1 max-h-72 overflow-auto rounded-md bg-muted px-3 py-2 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap break-all">
            {formatInput(item.tool, item.input)}
            {item.result !== null && (
              <>{item.input && Object.keys(item.input).length > 0 ? '\n\n' : ''}{item.result || '（无输出）'}</>
            )}
          </pre>
        </CollapsibleContent>
      </Collapsible>
    </li>
  )
}

function ToolIcon({ tool, denied }: { tool: string; denied: boolean }) {
  const className = 'size-3.5 shrink-0'
  if (denied) return <ShieldBan className={className} />
  if (tool === 'Bash') return <Terminal className={className} />
  if (tool === 'Read' || tool === 'Write' || tool === 'Edit') return <FileText className={className} />
  if (tool === 'Grep' || tool === 'Glob') return <Search className={className} />
  return <Wrench className={className} />
}

/** 展开时的输入：Bash 只显示命令，其余按 key: value 列出，长文本截断。 */
function formatInput(tool: string, input: Record<string, unknown>): string {
  if (tool === 'Bash' && typeof input.command === 'string') return `$ ${input.command}`
  return Object.entries(input)
    .map(([key, value]) => {
      const text = typeof value === 'string' ? value : JSON.stringify(value)
      return `${key}: ${text.length > 600 ? `${text.slice(0, 600)}…` : text}`
    })
    .join('\n')
}
