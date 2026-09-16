import { ChevronRight } from 'lucide-react'

import { ErrorNote } from '@/components/bits'
import { Markdown } from '@/components/Markdown'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { seconds, usd } from '@/lib/format'
import { toolSentence } from '@/lib/humanize'
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
    <article className="space-y-4" aria-label={`第 ${turn.n} 轮`}>
      <div className="flex justify-end">
        <p className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-[0.9375rem] leading-relaxed">
          {turn.message}
        </p>
      </div>
      {(trace.length > 0 || turn.live) && (
        <ol className="space-y-0.5">
          {trace.map((item, i) => <TraceRow key={i} item={item} />)}
          {turn.live && <Thinking />}
        </ol>
      )}
      {hasReply && <Markdown text={turn.reply!} />}
      {turn.outcome && (
        <p className="t-label tabular">
          {turn.outcome.failed ? '这一轮没走完' : '这一轮'}{' · '}{usd(turn.outcome.costUsd)}{' · '}{seconds(turn.outcome.durationS)}
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
    <li className="flex items-center gap-2.5 px-1 py-1.5 text-sm text-muted-foreground">
      <span className="relative flex size-2">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/60" />
        <span className="relative inline-flex size-2 rounded-full bg-primary" />
      </span>
      助理在想…
    </li>
  )
}

/** 助理按的一个按钮：正文是人话（「跑了基线」），原始命令与输出点开才看。 */
function TraceRow({ item }: { item: TraceItem }) {
  if (item.kind === 'error') return <li><ErrorNote text={item.text} /></li>
  if (item.kind === 'text') {
    return <li className="px-1 py-1"><Markdown text={item.text} className="text-muted-foreground" /></li>
  }
  const pending = item.result === null
  const status = item.denied ? '被拒绝了' : pending ? '进行中…' : item.isError ? '出错了' : ''
  return (
    <li>
      <Collapsible>
        <CollapsibleTrigger
          className={cn('group flex w-full items-center gap-2 rounded-md px-1.5 py-1.5 text-left text-sm transition-colors duration-150 hover:bg-muted',
                        item.denied ? 'text-bad' : item.isError ? 'text-warn' : 'text-muted-foreground')}
        >
          <ChevronRight className="size-3.5 shrink-0 transition-transform duration-150 group-data-[state=open]:rotate-90" />
          <span className="min-w-0 flex-1 truncate">
            {toolSentence(item.tool, item.input)}
            {status && <span className="ml-1.5">{status}</span>}
          </span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <pre className="mt-1 mb-2 max-h-72 overflow-auto rounded-md bg-muted px-3 py-2 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap break-all">
            {describeTool(item.tool, item.input)}
            {item.result !== null && <>{'\n\n'}{item.result || '（无输出）'}</>}
          </pre>
        </CollapsibleContent>
      </Collapsible>
    </li>
  )
}
