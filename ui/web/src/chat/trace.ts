// 一轮里的事件流怎么折成给人看的条目：文本合并成段、tool_use 与它的 tool_result 配成一对。
// 纯函数，不碰 React；页面上「agent 这一轮做了什么」全由这里决定。

import type { ChatEvent } from '@/api/types'

export type TraceItem =
  | { kind: 'text'; text: string; streaming?: boolean }
  | { kind: 'tool'; tool: string; input: Record<string, unknown>; result: string | null;
      isError: boolean; denied: boolean }
  | { kind: 'error'; text: string }

export interface TurnOutcome {
  costUsd: number | null
  durationS: number
  failed: boolean
}

export function reduceTrace(items: readonly TraceItem[], event: ChatEvent): TraceItem[] {
  switch (event.kind) {
    case 'delta': {
      // 逐字攒进正在说的那一段；上一段已经说完（或中间运行过命令）就另起一段
      const last = items[items.length - 1]
      if (last && last.kind === 'text' && last.streaming) {
        return [...items.slice(0, -1), { kind: 'text', text: last.text + event.text, streaming: true }]
      }
      return [...items, { kind: 'text', text: event.text, streaming: true }]
    }
    case 'text': {
      const last = items[items.length - 1]
      if (last && last.kind === 'text' && last.streaming) {
        // 完整的一段到了：用它替换攒出来的碎片，别拼两遍
        return [...items.slice(0, -1), { kind: 'text', text: event.text }]
      }
      if (last && last.kind === 'text') {
        return [...items.slice(0, -1), { kind: 'text', text: `${last.text}\n\n${event.text}` }]
      }
      return [...items, { kind: 'text', text: event.text }]
    }
    case 'tool_use':
      return [...items, { kind: 'tool', tool: event.tool, input: event.tool_input, result: null,
                          isError: false, denied: false }]
    case 'tool_result':
      return settle(items, { result: event.text, isError: event.is_error, denied: false })
    case 'denied':
      return settle(items, { result: event.text, isError: true, denied: true })
    case 'error':
      return [...items, { kind: 'error', text: event.text }]
    case 'init':
    case 'done':
      // done 的 text 与最后一段文本重复；成本与耗时由 outcome() 单独取
      return [...items]
  }
}

export function outcome(event: ChatEvent): TurnOutcome {
  return { costUsd: event.cost_usd, durationS: event.duration_s, failed: event.kind === 'error' }
}

/** 落盘的一轮（history 里的 events）重放成条目与结果：没有 done / error 就是没走完。
 *  走完了的一轮不可能还有工具在跑：没等到结果的工具行（老日志里 Codex 的 web_search 只记了调用）一律记成跑完、没输出。 */
export function replayTrace(events: readonly ChatEvent[]): { trace: TraceItem[]; outcome: TurnOutcome | null } {
  const folded = events.reduce<TraceItem[]>(reduceTrace, [])
  const last = [...events].reverse().find((e) => e.kind === 'done' || e.kind === 'error')
  const trace = last
    ? folded.map((item) => (item.kind === 'tool' && item.result === null ? { ...item, result: '' } : item))
    : folded
  return { trace, outcome: last ? outcome(last) : null }
}

/** 把结果挂到最近一个还没有结果的工具调用上。没有待结果的调用（被拒的命令会同时来一条 denied
 *  和一条 tool_result）就追加到最近那个工具行上，别当成助理说的话显示出来；一个工具行都没有才当文本。 */
function settle(
  items: readonly TraceItem[],
  patch: { result: string; isError: boolean; denied: boolean },
): TraceItem[] {
  let lastTool = -1
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i]
    if (item.kind !== 'tool') continue
    if (item.result === null) {
      return [...items.slice(0, i), { ...item, ...patch }, ...items.slice(i + 1)]
    }
    if (lastTool === -1) lastTool = i
  }
  if (lastTool === -1) return [...items, { kind: 'text', text: patch.result }]
  const item = items[lastTool] as Extract<TraceItem, { kind: 'tool' }>
  if (item.result === patch.result) return [...items]
  const merged = { ...item, result: `${item.result}\n\n${patch.result}`, isError: item.isError || patch.isError,
                   denied: item.denied || patch.denied }
  return [...items.slice(0, lastTool), merged, ...items.slice(lastTool + 1)]
}

/** 跑命令的工具：Claude Code 叫 Bash，Codex 叫 shell（命令外面还裹着一层 `/bin/zsh -lc '…'`，给人看要剥掉） */
const COMMAND_TOOLS = new Set(['Bash', 'shell'])
const SHELL_WRAP = /^\/bin\/(?:zsh|bash|sh) -lc '([\s\S]*)'$/

/** 一次命令调用里那条命令本身；不是命令工具就是 null */
export function commandOf(tool: string, input: Record<string, unknown>): string | null {
  if (!COMMAND_TOOLS.has(tool)) return null
  const raw = typeof input.command === 'string' ? input.command : tool
  return SHELL_WRAP.exec(raw)?.[1] ?? raw
}

/** 工具调用里给人看的那个东西：路径、搜索词、改了哪些文件；都没有就是 null */
function subjectOf(input: Record<string, unknown>): string | null {
  const str = (key: string) => (typeof input[key] === 'string' && input[key] ? (input[key] as string) : null)
  const path = str('file_path') ?? str('path') ?? str('pattern')
  if (path) return path
  const query = str('query')
  if (query) return query
  const changes = Array.isArray(input.changes) ? input.changes.filter((c) => typeof c === 'string') : []
  return changes.length ? changes.join('\n') : null
}

/** 工具调用的原样：命令就是那条命令，读写文件是「工具名 路径」，搜索是「工具名 搜索词」，其余是工具名。展开层用它。 */
export function describeTool(tool: string, input: Record<string, unknown>): string {
  const command = commandOf(tool, input)
  if (command !== null) return command
  const subject = subjectOf(input)
  return subject ? `${tool} ${subject}` : tool
}

/** 对话里的那一行：同 describeTool，只是命令只留第一行、路径只留末两段（`Read design/1/scoring.yaml`）、改动只留第一条。 */
export function toolLine(tool: string, input: Record<string, unknown>): string {
  const command = commandOf(tool, input)
  if (command !== null) return command.split('\n')[0]
  const subject = subjectOf(input)?.split('\n')[0]
  if (!subject) return tool
  if (typeof input.query === 'string' && subject === input.query) return `${tool} ${subject}`
  const parts = subject.split('/').filter(Boolean)
  return `${tool} ${parts.slice(-2).join('/')}`
}
