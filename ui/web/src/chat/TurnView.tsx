import { CaretRight } from '@phosphor-icons/react'

import { ErrorNote } from '@/components/bits'
import { Markdown } from '@/components/Markdown'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { seconds, splitLede, usd } from '@/lib/format'
import { denialSentence, toolSentence, wakeSentence } from '@/lib/humanize'
import { cn } from '@/lib/utils'

import { describeTool, type TraceItem, type TurnOutcome } from './trace'

export interface Turn {
  n: number
  /** 谁开的口：研究者，或框架（后台作业跑完来叫醒助理） */
  origin: '人' | '框架'
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
  const tools = trace.filter((item) => item.kind === 'tool').length
  const foldable = !turn.live && hasReply && trace.length > 0
  const rows = (
    <ol className="space-y-0.5">
      {trace.map((item, i) => <TraceRow key={i} item={item} />)}
      {turn.live && <Thinking />}
    </ol>
  )
  return (
    <article className="space-y-4" aria-label={`第 ${turn.n} 轮`}>
      {turn.origin === '框架' ? (
        <p className="flex items-center justify-center gap-2 text-[0.8125rem] text-muted-foreground">
          <span className="rounded-sm border px-1.5 py-px text-[0.6875rem] leading-tight">框架</span>
          {wakeSentence(turn.message)}
        </p>
      ) : (
        <div className="flex justify-end">
          <p className="max-w-[78%] rounded-[18px_18px_4px_18px] bg-accent px-4 py-2.5 text-[0.9375rem] leading-relaxed whitespace-pre-wrap text-accent-foreground">
            {turn.message}
          </p>
        </div>
      )}
      {foldable ? (
        <Collapsible>
          <CollapsibleTrigger className="group flex items-center gap-1.5 text-[0.8125rem] text-muted-foreground hover:text-foreground">
            <CaretRight className="size-3.5 transition-transform duration-150 group-data-[state=open]:rotate-90" />
            助理做了 {tools} 件事
          </CollapsibleTrigger>
          <CollapsibleContent className="mt-2 border-l-2 pl-3">{rows}</CollapsibleContent>
        </Collapsible>
      ) : (trace.length > 0 || turn.live) && rows}
      {hasReply && <Reply text={turn.reply!} />}
      {turn.outcome && (
        <p className="t-label tabular">
          {turn.outcome.failed ? '没走完，' : ''}{usd(turn.outcome.costUsd)}，{seconds(turn.outcome.durationS)}
        </p>
      )}
    </article>
  )
}

/** 助理的回答：开头那句结论用宋体立起来（指南要它先说结论），其余照 Markdown 排。 */
function Reply({ text }: { text: string }) {
  const { lede, rest } = splitLede(text)
  return (
    <div className="space-y-2">
      {lede && <p className="t-lede">{lede}</p>}
      {rest && <Markdown text={rest} />}
    </div>
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

/** 助理做的一件事：正文是人话（「跑了基线」），原始命令与输出点开才看。 */
function TraceRow({ item }: { item: TraceItem }) {
  if (item.kind === 'error') return <li><ErrorNote text={item.text} /></li>
  if (item.kind === 'text') {
    return (
      <li className="px-1 py-1">
        <Markdown text={item.text} className="text-muted-foreground" />
        {item.streaming && (
          <span aria-hidden className="ml-0.5 inline-block h-[1em] w-0.5 animate-pulse bg-primary align-[-2px]" />
        )}
      </li>
    )
  }
  const pending = item.result === null
  const status = item.denied ? '（被拒）' : pending ? '…' : item.isError ? '（出错）' : ''
  return (
    <li>
      <Collapsible>
        <CollapsibleTrigger
          className={cn('group flex w-full items-center gap-2 rounded-md px-1.5 py-1.5 text-left text-sm transition-colors duration-150 hover:bg-muted',
                        item.denied ? 'text-bad' : item.isError ? 'text-warn' : 'text-muted-foreground')}
        >
          <CaretRight className="size-3.5 shrink-0 transition-transform duration-150 group-data-[state=open]:rotate-90" />
          <span className="min-w-0 flex-1 truncate">
            {toolSentence(item.tool, item.input)}
            {status && <span>{status}</span>}
          </span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <pre className="mt-1 mb-2 max-h-72 overflow-auto rounded-md bg-muted px-3 py-2 font-mono text-[11.5px] leading-relaxed whitespace-pre-wrap break-all">
            {describeTool(item.tool, item.input)}
            {item.result !== null && <>{'\n\n'}{item.denied ? denialSentence(item.result) : item.result || '（无输出）'}</>}
          </pre>
        </CollapsibleContent>
      </Collapsible>
    </li>
  )
}
