import { describe, expect, it } from 'vitest'

import type { ChatEvent } from '@/api/types'

import { commandOf, describeTool, reduceTrace, replayTrace, toolLine } from './trace'

const ev = (partial: Partial<ChatEvent> & { kind: ChatEvent['kind'] }): ChatEvent => ({
  text: '', tool: '', tool_input: {}, is_error: false, session_id: 's', cost_usd: null,
  duration_s: 0, exit_code: null, ...partial,
})

const fold = (events: ChatEvent[]) => events.reduce(reduceTrace, [])

describe('reduceTrace', () => {
  it('合并相邻文本，done 不重复最后一段', () => {
    const items = fold([
      ev({ kind: 'init' }), ev({ kind: 'text', text: '先看' }), ev({ kind: 'text', text: '再说' }),
      ev({ kind: 'done', text: '再说', cost_usd: 0.01 }),
    ])
    expect(items).toEqual([{ kind: 'text', text: '先看\n\n再说' }])
  })

  it('tool_use 与 tool_result 配对，denied 记成拒绝', () => {
    const items = fold([
      ev({ kind: 'tool_use', tool: 'Bash', tool_input: { command: 'ls' } }),
      ev({ kind: 'tool_result', text: 'a\nb' }),
      ev({ kind: 'tool_use', tool: 'Bash', tool_input: { command: 'rm x' } }),
      ev({ kind: 'denied', text: '不许' }),
      ev({ kind: 'text', text: '好' }),
    ])
    expect(items).toEqual([
      { kind: 'tool', tool: 'Bash', input: { command: 'ls' }, result: 'a\nb', isError: false,
        denied: false },
      { kind: 'tool', tool: 'Bash', input: { command: 'rm x' }, result: '不许', isError: true,
        denied: true },
      { kind: 'text', text: '好' },
    ])
  })

  it('孤儿结果与 error 都直接显示，不丢', () => {
    const items = fold([ev({ kind: 'tool_result', text: '孤儿' }), ev({ kind: 'error', text: '超时' })])
    expect(items).toEqual([{ kind: 'text', text: '孤儿' }, { kind: 'error', text: '超时' }])
  })

  it('被拒绝后再来的 tool_result 挂到那个工具行上，不当成助理的话', () => {
    const items = fold([
      ev({ kind: 'tool_use', tool: 'Bash', tool_input: { command: 'cat x' } }),
      ev({ kind: 'denied', text: '不许' }),
      ev({ kind: 'tool_result', text: 'Permission denied…', is_error: true }),
    ])
    expect(items).toEqual([
      { kind: 'tool', tool: 'Bash', input: { command: 'cat x' }, result: '不许\n\nPermission denied…',
        isError: true, denied: true },
    ])
  })
})

describe('describeTool', () => {
  it('Bash 显示命令，文件工具显示路径，搜索显示搜索词，其余显示工具名', () => {
    expect(describeTool('Bash', { command: 'ai4sci show workspaces' })).toBe('ai4sci show workspaces')
    expect(describeTool('Read', { file_path: '/x/scoring.yaml' })).toBe('Read /x/scoring.yaml')
    expect(describeTool('WebSearch', { query: 'q' })).toBe('WebSearch q')
    expect(describeTool('WebSearch', {})).toBe('WebSearch')
  })

  it('Codex 的 shell 剥掉 /bin/zsh -lc 那层壳，apply_patch 列改动', () => {
    expect(commandOf('shell', { command: "/bin/zsh -lc 'ai4sci show project'" })).toBe('ai4sci show project')
    expect(commandOf('shell', { command: "/bin/bash -lc 'rg -n \"Table 8\" a.md'" })).toBe('rg -n "Table 8" a.md')
    expect(commandOf('shell', { command: 'ls' })).toBe('ls')
    expect(commandOf('Read', { file_path: '/x' })).toBeNull()
    expect(describeTool('shell', { command: "/bin/zsh -lc 'ai4sci show project'" })).toBe('ai4sci show project')
    expect(describeTool('apply_patch', { changes: ['add a/b.py', 'update c.md'] })).toBe('apply_patch add a/b.py\nupdate c.md')
    expect(describeTool('web_search', { query: 'GUA PINN', action: 'search' })).toBe('web_search GUA PINN')
  })
})

describe('delta 逐字攒段', () => {
  const ev = (kind: ChatEvent['kind'], text: string): ChatEvent =>
    ({ kind, text, tool: '', tool_input: {}, is_error: false, session_id: null, cost_usd: null,
       duration_s: 0, exit_code: null })

  it('片段攒进正在说的那段，完整 text 到了整段替换、不拼两遍', () => {
    let items = reduceTrace([], ev('delta', '基线'))
    items = reduceTrace(items, ev('delta', '跑完了'))
    expect(items).toEqual([{ kind: 'text', text: '基线跑完了', streaming: true }])
    items = reduceTrace(items, ev('text', '基线跑完了。'))
    expect(items).toEqual([{ kind: 'text', text: '基线跑完了。' }])
    items = reduceTrace(items, ev('delta', '下一步'))
    expect(items).toHaveLength(2)
    expect(items[1]).toEqual({ kind: 'text', text: '下一步', streaming: true })
  })
})

describe('toolLine', () => {
  it('命令原样只留第一行，路径只留末两段', () => {
    expect(toolLine('Bash', { command: 'ai4sci show workspace' })).toBe('ai4sci show workspace')
    expect(toolLine('Bash', { command: 'ls -1\nls -2' })).toBe('ls -1')
    expect(toolLine('Read', { file_path: '/a/b/design/1/scoring.yaml' })).toBe('Read 1/scoring.yaml')
    expect(toolLine('Read', { file_path: '/a/b/w/requirement.md' })).toBe('Read w/requirement.md')
    expect(toolLine('Grep', { pattern: 'x' })).toBe('Grep x')
    expect(toolLine('WebSearch', {})).toBe('WebSearch')
  })

  it('Codex 的工具也是它本来的样子：命令、搜索词整句、改动只留第一条', () => {
    expect(toolLine('shell', { command: "/bin/zsh -lc 'ai4sci show project'" })).toBe('ai4sci show project')
    expect(toolLine('web_search', { query: 'site:arxiv.org 2609.01558', action: 'search' })).toBe('web_search site:arxiv.org 2609.01558')
    expect(toolLine('apply_patch', { changes: ['add workspaces/w/requirement.md', 'update b'] })).toBe('apply_patch w/requirement.md')
    expect(toolLine('apply_patch', { changes: [] })).toBe('apply_patch')
  })
})

describe('replayTrace', () => {
  it('落盘的事件重放成条目，done 给结果；没有 done 就是没走完', () => {
    const events = [
      ev({ kind: 'init' }), ev({ kind: 'tool_use', tool: 'Bash', tool_input: { command: 'ls' } }),
      ev({ kind: 'tool_result', text: 'a\nb' }), ev({ kind: 'text', text: '两个' }),
      ev({ kind: 'done', text: '两个', cost_usd: 0.02, duration_s: 3 }),
    ]
    const { trace, outcome } = replayTrace(events)
    expect(trace.map((t) => t.kind)).toEqual(['tool', 'text'])
    expect(outcome).toEqual({ costUsd: 0.02, durationS: 3, failed: false })
    expect(replayTrace(events.slice(0, 3)).outcome).toBeNull()
    expect(replayTrace([]).trace).toEqual([])
  })

  it('走完了的一轮里没等到结果的工具行记成跑完；没走完的照旧算在跑', () => {
    const search = ev({ kind: 'tool_use', tool: 'web_search', tool_input: { query: 'q' } })
    const finished = replayTrace([search, ev({ kind: 'done', text: '' })]).trace[0]
    expect(finished.kind === 'tool' && finished.result).toBe('')
    const live = replayTrace([search]).trace[0]
    expect(live.kind === 'tool' && live.result).toBeNull()
  })
})
