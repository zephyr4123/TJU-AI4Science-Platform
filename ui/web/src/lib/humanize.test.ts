import { describe, expect, it } from 'vitest'

import type { LedgerRow, RunSummary, TaskSummary } from '@/api/types'

import {
  budgetSentence, conclusionOf, gateSentence, goalSentence, roundSentence, runVerdict,
  stopSentence, toolSentence, trustChecks,
} from './humanize'

const row = (partial: Partial<LedgerRow>): LedgerRow => ({
  iter: 1, commit: 'abc', parent: '-', metric: null, direction: 'minimize', elapsed_s: null,
  seed: 42, status: 'keep', sigma: null, harness_sha: 'x', note: '', cost_usd: null,
  executor_s: null, ...partial,
})

const run = (partial: Partial<RunSummary>): RunSummary => ({
  run_id: 'r', task: 't', title: 't', metric: { name: 'nll', direction: 'minimize' },
  baseline: 21.6, best_metric: 21.34, best_iter: 6, last_iter: 8, stop_reason: null,
  updated_at: null, cost_usd: 1.25, running: false, job: null, analysis: true,
  verify: { status: 'PASS' }, accept: null, ...partial,
})

describe('任务包的句子', () => {
  it('怎么算好', () => {
    const task = { metric: { name: 'nll_mean', direction: 'minimize', attainable: 21.18 } } as TaskSummary
    expect(goalSentence(task, 21.5958)).toBe('看 nll_mean，越小越好，现在的基线是 21.6，已知的尽头大约是 21.18。')
    expect(goalSentence({ metric: null } as TaskSummary)).toBe('还没定下用哪个数来评判。')
  })
  it('预算与门槛', () => {
    expect(budgetSentence({ max_iterations: 30, wall_clock_s: 75, max_cost_usd: 5 }))
      .toBe('最多改 30 轮，每轮跑分不超过 1 min 15 s，执行层总共不超过 $5.00。')
    expect(gateSentence(0.076, 0.152, 2.7)).toContain('好过 0.152 才算真的改进，从基线到尽头有 2.7 个')
    expect(gateSentence(undefined, undefined, null)).toBeNull()
  })
})

describe('run 的句子', () => {
  it('逐轮', () => {
    expect(roundSentence(row({ iter: 6, status: 'keep', metric: 21.34 }), 21.6, 'minimize')).toBe('第 6 轮：留下，好了 0.26')
    expect(roundSentence(row({ iter: 7, status: 'discard', metric: 21.28, note: 'within noise: delta=0.05 <= gate=0.15' }), 21.34, 'minimize'))
      .toBe('第 7 轮：好了一点但在噪声里，不算')
    expect(roundSentence(row({ iter: 2, status: 'discard', metric: 21.6, note: '变差或持平 delta=0' }), 21.6, 'minimize'))
      .toBe('第 2 轮：成绩没变，改动大概没生效')
    expect(roundSentence(row({ iter: 3, status: 'executor_failed' }), 21.6, 'minimize')).toBe('第 3 轮：助手出错，这轮没算')
  })
  it('结论与可信度', () => {
    expect(runVerdict(run({}), 0.26, 0.15).headline).toBe('比原来好了 0.26，相当于 1.7 个噪声门槛，数字都能回溯。可以验收。')
    expect(runVerdict(run({ verify: null }), 0.26, null).tone).toBe('warn')
    expect(runVerdict(run({ running: true }), 0.26, null).headline).toBe('实验还在跑，先别下结论。')
    expect(runVerdict(run({ last_iter: 0 }), null, null).headline).toBe('还没改过一轮，只有基线。')
    expect(trustChecks(run({ verify: null, analysis: false })).map((c) => c.ok)).toEqual([null, true, false])
    expect(stopSentence('patience', false)).toBe('连续几轮都没进步，停了')
    expect(stopSentence(null, true)).toBe('正在跑')
  })
  it('抽结论一节', () => {
    const doc = '# 分析\n\n## 结论\n\nbest 是第 6 轮。\n\n## 数据\n\n| a |\n'
    expect(conclusionOf(doc)).toBe('best 是第 6 轮。')
    expect(conclusionOf('没有小节')).toBe('没有小节')
  })
})

describe('工具行', () => {
  it('命令翻成动作', () => {
    expect(toolSentence('Bash', { command: '.venv/bin/ai4sci cap baseline tasks/x' })).toBe('跑了基线')
    expect(toolSentence('Bash', { command: 'ai4sci cap experiment r1 --resume' })).toBe('接着跑上次没走完的实验')
    expect(toolSentence('Bash', { command: 'ai4sci show task tasks/x' })).toBe('校验了任务包')
    expect(toolSentence('Bash', { command: 'ai4sci show tasks' })).toBe('看了一眼有哪些任务包')
    expect(toolSentence('Bash', { command: 'ls -1 tasks/' })).toBe('看了目录')
    expect(toolSentence('Bash', { command: 'python3 -c 1' })).toBe('跑了一条命令')
    expect(toolSentence('Read', { file_path: '/a/b/tasks/x/manifest.yaml' })).toBe('读了 x/manifest.yaml')
    expect(toolSentence('Grep', { pattern: 'a' })).toBe('搜了文件')
  })
})
