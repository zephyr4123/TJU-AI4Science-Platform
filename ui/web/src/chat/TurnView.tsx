import { CaretRight, File, Globe, type Icon, MagnifyingGlass, Terminal, Wrench } from '@phosphor-icons/react'
import { useReducedMotion } from 'motion/react'
import { createElement } from 'react'

import { ErrorNote } from '@/components/bits'
import { Markdown } from '@/components/Markdown'
import ShinyText from '@/components/reactbits/ShinyText'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { seconds, usd } from '@/lib/format'
import { denialSentence, wakeSentence } from '@/lib/humanize'
import { useToken } from '@/lib/tokens'
import { cn } from '@/lib/utils'

import { describeTool, toolLine, type TraceItem, type TurnOutcome } from './trace'

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

/** `thinking` 是助理想着时那个词（随选的思考深度变），只有跑着的那一轮用得上 */
export function TurnView({ turn, thinking = 'thinking' }: { turn: Turn; thinking?: string }) {
  const hasReply = turn.reply !== null && turn.reply !== ''
  // 回答已经落盘的轮次，trace 里的最后一段文本就是回答本身，不重复显示
  const trace = hasReply && !turn.live ? withoutTrailingText(turn.trace) : turn.trace
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
      {(trace.length > 0 || turn.live) && (
        <ol className="space-y-0.5">
          {trace.map((item, i) => <TraceRow key={i} item={item} />)}
          {turn.live && <Thinking word={thinking} />}
        </ol>
      )}
      {hasReply && <Reply text={turn.reply!} />}
      {turn.outcome && (
        <p className="t-label tabular">
          {turn.outcome.failed ? '没走完，' : ''}{usd(turn.outcome.costUsd)}，{seconds(turn.outcome.durationS)}
        </p>
      )}
    </article>
  )
}

/** 助理的回答：照普通 Markdown 排，排版交给它自己（主人：别限得这么死；原来「开头一句拎成宋体结论」的规则把短回复整条变成大号粗体）。 */
function Reply({ text }: { text: string }) {
  return <Markdown text={text} />
}

function withoutTrailingText(items: TraceItem[]): TraceItem[] {
  const last = items[items.length - 1]
  return last && last.kind === 'text' ? items.slice(0, -1) : items
}

/** 助理想着：一个英文词（thinking / hard thinking / …，随选的深度变），reactbits ShinyText 让光从字上扫过；减少动效时静态。 */
function Thinking({ word }: { word: string }) {
  const still = useReducedMotion()
  const muted = useToken('--muted-foreground')
  const indigo = useToken('--primary')
  return (
    <li className="flex items-center gap-2.5 px-1 py-1.5 text-sm text-muted-foreground">
      <span className="relative flex size-2">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/60 motion-reduce:animate-none" />
        <span className="relative inline-flex size-2 rounded-full bg-primary" />
      </span>
      {still ? <span className="font-mono lowercase">{word}</span>
             : <ShinyText text={word} color={muted} shineColor={indigo} speed={2} className="font-mono lowercase" />}
    </li>
  )
}

/** 工具图标：命令是终端，读写文件是文件，搜索是放大镜，网页是地球，其余扳手 */
const TOOL_ICON: Record<string, Icon> = {
  Bash: Terminal, Read: File, Write: File, Edit: File, Grep: MagnifyingGlass, Glob: MagnifyingGlass,
  WebSearch: Globe, WebFetch: Globe,
}

/** 一条工具调用，就是它本来的样子：`ai4sci show workspace`、`Read design/1/scoring.yaml`；点开看输出。它是对话的一部分，一直留着。 */
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
  const status = item.denied ? '被拒' : item.isError ? '出错' : ''
  const icon = TOOL_ICON[item.tool] ?? Wrench
  return (
    <li>
      <Collapsible>
        <CollapsibleTrigger
          className={cn('group flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left font-mono text-[0.8125rem] transition-colors duration-150 hover:bg-muted',
                        item.denied ? 'text-bad' : item.isError ? 'text-warn' : 'text-muted-foreground')}
        >
          {createElement(icon, { 'aria-hidden': true, className: 'size-3.5 shrink-0' })}
          <span className="min-w-0 flex-1 truncate">{toolLine(item.tool, item.input)}</span>
          {pending && <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-primary" aria-label="运行中" />}
          {status && <span className="shrink-0 text-[0.75rem]">{status}</span>}
          <CaretRight className="size-3 shrink-0 opacity-0 transition-[transform,opacity] duration-150 group-hover:opacity-100 group-data-[state=open]:rotate-90 group-data-[state=open]:opacity-100" />
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
