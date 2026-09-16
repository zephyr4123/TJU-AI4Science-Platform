// 进度页的算术：五步的状态与两句话，从任务包与 run 的真实文件推出来。纯函数，有单测。

import type { RunSummary, TaskSummary } from '@/api/types'

import { STAGE_NEXT } from './humanize'

export const STEPS = ['接任务', '跑基线', '做实验', '写分析', '验证'] as const
export type StepState = 'done' | 'current' | 'todo'

interface Progress {
  states: StepState[]
  now: string
  next: string
  run: RunSummary | null
}

/** 五步的状态与两句话；纯函数，便于单测。 */
export function progressOf(task: TaskSummary, runs: RunSummary[]): Progress {
  const mine = runs.filter((r) => r.task === task.id)
    .sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? ''))
  const run = mine[0] ?? null
  const done = [
    task.stage === 'designed' || task.stage === 'baselined',
    task.stage === 'baselined',
    run !== null && run.last_iter > 0,
    run !== null && run.analysis,
    run !== null && run.verify?.status === 'PASS',
  ]
  const firstTodo = done.indexOf(false)
  const states = done.map((d, i): StepState => (d ? 'done' : i === firstTodo ? 'current' : 'todo'))
  if (task.stage === 'drafting') {
    return { states, run, now: '需求还没发布，什么都还没开始。', next: STAGE_NEXT.drafting }
  }
  if (firstTodo === -1) {
    return { states, run, now: `五步都走完了${run?.accept && !run.accept.stale ? '，结果已验收' : ''}。`,
             next: run?.accept && !run.accept.stale ? '可以开下一个课题了。' : '到「结果」页看一眼，能用就验收。' }
  }
  const NOW = ['等助理接任务。', '等助理跑基线。', run?.running ? '实验正在跑。' : run ? '实验跑过了，还没有留下改进。' : '基线跑完，等开实验。',
               '实验有结果了，等写分析。', '分析写好了，等验证数字。']
  const NEXT = [STAGE_NEXT.published, STAGE_NEXT.designed, run ? '在对话里让助理继续跑，或者换个思路。' : STAGE_NEXT.baselined,
                '在对话里让助理写分析。', '在对话里让助理验证。验证通过再验收。']
  return { states, run, now: NOW[firstTodo], next: NEXT[firstTodo] }
}
