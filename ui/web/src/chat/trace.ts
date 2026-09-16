// 一轮里的事件流怎么折成给人看的条目：文本合并成段、tool_use 与它的 tool_result 配成一对。
// 纯函数，不碰 React；页面上「agent 这一轮按了什么」全由这里决定。

import type { ChatEvent } from '@/api/types'

export type TraceItem =
  | { kind: 'text'; text: string }
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
    case 'text': {
      const last = items[items.length - 1]
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

/** 把结果挂到最近一个还没有结果的工具调用上。没有待结果的调用（被拒绝的按钮会同时来一条 denied
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

/** 工具调用给人看的一句话：Bash 显示命令，读写文件显示路径，其余显示工具名。 */
export function describeTool(tool: string, input: Record<string, unknown>): string {
  const str = (key: string) => (typeof input[key] === 'string' ? (input[key] as string) : null)
  if (tool === 'Bash') return str('command') ?? 'Bash'
  const path = str('file_path') ?? str('path') ?? str('pattern')
  return path ? `${tool} ${path}` : tool
}
