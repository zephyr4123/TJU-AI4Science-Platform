// 把框架的状态码、判决、命令翻成研究者看得懂的句子。页面正文只许用这里的输出；
// 原始值（状态码、哈希、命令）只在展开层出现。纯函数，有单测。

import type { Direction, LedgerRow, RunSummary, Stage, TaskSummary } from '@/api/types'

import { prose, seconds, usd } from './format'

// ── 任务包 ────────────────────────────────────────────────────────────────
export const STAGE_LABEL: Record<Stage, string> = {
  drafting: '还没发布', published: '已发布，等助理接任务', designed: '助理已接任务，等跑基线',
  baselined: '基线跑完，可以开实验',
}

export const STAGE_NEXT: Record<Stage, string> = {
  drafting: '看完下面几段，确认这就是你要的，署名发布。',
  published: '在对话里让助理接任务：它会写裁判脚本和基线草稿。',
  designed: '在对话里让助理跑基线，机器会顺便算有没有改进空间。',
  baselined: '在对话里让助理开实验。跑完到「结果」页看。',
}

export function directionWord(direction: Direction | undefined): string {
  return direction === 'maximize' ? '越大越好' : '越小越好'
}

/** 「怎么算好」一句话：指标、方向、现在的基线、谷底。 */
export function goalSentence(task: TaskSummary, baseline?: number | null): string {
  if (!task.metric) return '还没定下用哪个数来评判。'
  const parts = [`看 ${task.metric.name}，${directionWord(task.metric.direction)}`]
  if (baseline != null) parts.push(`现在的基线是 ${prose(baseline)}`)
  if (task.metric.attainable != null) parts.push(`已知的尽头大约是 ${prose(task.metric.attainable)}`)
  return `${parts.join('，')}。`
}

/** 预算一句话：只挑研究者会关心的三样。 */
export function budgetSentence(budget: Record<string, unknown>): string {
  const parts: string[] = []
  const rounds = num(budget.max_iterations)
  const wall = num(budget.wall_clock_s)
  const cost = num(budget.max_cost_usd)
  if (rounds != null) parts.push(`最多改 ${rounds} 轮`)
  if (wall != null) parts.push(`每轮跑分不超过 ${seconds(wall)}`)
  if (cost != null) parts.push(`执行层总共不超过 ${usd(cost)}`)
  return parts.length ? `${parts.join('，')}。` : '预算还没定。'
}

export function budgetNumbers(budget: Record<string, unknown>): { label: string; value: number | null; unit: string }[] {
  return [
    { label: '最多改几轮', value: num(budget.max_iterations), unit: '轮' },
    { label: '每轮跑分上限', value: num(budget.wall_clock_s), unit: '秒' },
    { label: '花费上限', value: num(budget.max_cost_usd), unit: '美元' },
  ]
}

/** 噪声门一句话：预检算出来的门槛，说成人话。 */
export function gateSentence(sigma: number | undefined, gate: number | undefined,
                             gates: number | null | undefined): string | null {
  if (sigma === undefined || gate === undefined) return null
  let text = `同一份代码重复跑，成绩会晃动约 ${prose(sigma)}；所以只有好过 ${prose(gate)} 才算真的改进`
  if (gates != null && Number.isFinite(gates)) text += `，从基线到尽头有 ${gates.toFixed(1)} 个这样的门槛的空间`
  else if (gates != null) text += '，尽头没有上限'
  return `${text}。`
}

// ── run ──────────────────────────────────────────────────────────────────
export const STATUS_SENTENCE: Record<string, string> = {
  keep: '留下', discard: '没留', timeout: '跑超时了，没算', crash: '跑崩了，没算',
  no_results: '没出结果，没算', readonly_violated: '改了不该改的文件，作废',
  noop: '什么都没改', interrupted: '中途被打断', executor_failed: '助手出错，这轮没算',
}

/** 一轮一句：「第 6 轮：留下，好了 0.26」。 */
export function roundSentence(row: LedgerRow, best: number | null, direction: Direction): string {
  const head = `第 ${row.iter} 轮`
  if (row.status === 'keep' && row.metric != null && best != null) {
    const gain = direction === 'minimize' ? best - row.metric : row.metric - best
    return `${head}：留下，好了 ${prose(Math.abs(gain))}`
  }
  if (row.status === 'discard' && row.metric != null) {
    if (/within noise|噪声/.test(row.note)) return `${head}：好了一点但在噪声里，不算`
    if (/delta=0(?![.\d])/.test(row.note) || /没有生效/.test(row.note)) return `${head}：成绩没变，改动大概没生效`
    return `${head}：变差了，没留`
  }
  return `${head}：${STATUS_SENTENCE[row.status] ?? row.status}`
}

export const STOP_SENTENCE: Record<string, string> = {
  patience: '连续几轮都没进步，停了',
  max_iterations: '轮数用完了',
  max_cost_usd: '花费到上限了',
  unrecoverable: '同一种错连着出，停下来等人看',
  batch_exhausted: '这一批跑完了，可以再跑',
}

export function stopSentence(reason: string | null, running: boolean): string {
  if (running) return '正在跑'
  if (!reason) return '没在跑，随时可以继续'
  return STOP_SENTENCE[reason] ?? `停了：${reason}`
}

export interface Verdict {
  tone: 'ok' | 'warn' | 'neutral'
  headline: string
}

/** 结果页的一句话结论。 */
export function runVerdict(run: RunSummary, delta: number | null, gate: number | null): Verdict {
  if (run.running) return { tone: 'warn', headline: '实验还在跑，先别下结论。' }
  if (run.last_iter === 0) return { tone: 'neutral', headline: '还没改过一轮，只有基线。' }
  if (delta === null) return { tone: 'neutral', headline: '基线数据缺失，比不了。' }
  if (delta <= 0) return { tone: 'neutral', headline: '没有比原来好，改动都没留下。' }
  const gates = gate && gate > 0 ? `，相当于 ${(delta / gate).toFixed(1)} 个噪声门槛` : ''
  const better = `比原来好了 ${prose(delta)}${gates}`
  if (run.verify?.status === 'PASS') {
    return { tone: 'ok', headline: `${better}，数字都能回溯。可以验收。` }
  }
  if (run.verify?.status === 'FAIL') {
    return { tone: 'warn', headline: `${better}，但分析里有对不上的数，先别验收。` }
  }
  return { tone: 'warn', headline: `${better}，但还没验证过，验收前让助理先验证。` }
}

/** 可信度三项，每项一句。 */
export function trustChecks(run: RunSummary): { ok: boolean | null; text: string }[] {
  const verify = run.verify?.status
  return [
    { ok: verify === 'PASS' ? true : verify ? false : null,
      text: verify === 'PASS' ? '分析里的每个数都能回溯到某一轮的结果文件'
        : verify === 'FAIL' ? '分析里有对不上结果文件的数' : verify === 'invalid' ? '验证报告坏了，要重跑'
        : '还没验证：分析里的数还没和结果文件对过' },
    { ok: true, text: '每一轮的改动都记了账，留下的都对得上代码历史' },
    { ok: run.analysis, text: run.analysis ? '分析已经写好' : '分析还没写' },
  ]
}

/** 从 analysis.md 里抽「结论」一节；没有就退回全文。 */
export function conclusionOf(analysis: string): string {
  const match = /^##\s*结论\s*\n([\s\S]*?)(?=^##\s|\s*$)/m.exec(analysis)
  return (match ? match[1] : analysis).trim()
}

// ── 能力清单 ─────────────────────────────────────────────────────────────
// 能力的人话标题与说明（title / what）与所属阶段都在描述符里，页面直接读 `/cap`，这里不再另抄一份。
export const LEVEL_COPY: Record<string, string> = {
  task: '在任务包上做', run: '在一次实验里做', project: '在整个项目上做',
}

// ── 对话里的工具行 ────────────────────────────────────────────────────────
// 每条命令一句直白的话：查了什么、运行了什么、写了什么。带 --detach 的加一句「放到后台跑」。
const CLI_SENTENCE: [RegExp, string][] = [
  [/ai4sci cap init/, '起了任务包'],
  [/ai4sci cap design/, '接了任务：写裁判脚本和基线草稿'],
  [/ai4sci cap baseline/, '跑了基线'],
  [/ai4sci cap start/, '开了一次实验'],
  [/ai4sci cap experiment.*--resume/, '接着跑上次没走完的实验'],
  [/ai4sci cap experiment/, '跑了几轮实验'],
  [/ai4sci cap analysis/, '写了分析'],
  [/ai4sci cap verify/, '验证了分析里的数字'],
  [/ai4sci sign task/, '替人发布了需求（这件事应该由人做）'],
  [/ai4sci sign run/, '替人验收了结果（这件事应该由人做）'],
  [/ai4sci show tasks/, '查了有哪些任务包'],
  [/ai4sci show task\b/, '检查了任务包'],
  [/ai4sci show runs?\b/, '查了实验进度'],
  [/ai4sci show jobs?\b/, '查了后台作业'],
  [/ai4sci show caps/, '查了有哪些能力'],
  [/ai4sci show workflows/, '查了有哪些工作流'],
  [/ai4sci show flow/, '检查了这样拼通不通'],
  [/^\s*(ls|find|tree)\b/, '看了目录'],
  [/^\s*(cat|head|tail|sed -n)\b/, '读了文件'],
  [/^\s*(grep|rg)\b/, '搜了文件内容'],
]

/** 工具行的人话：命令翻成动作；文件工具带文件名。 */
export function toolSentence(tool: string, input: Record<string, unknown>): string {
  const str = (key: string) => (typeof input[key] === 'string' ? (input[key] as string) : null)
  if (tool === 'Bash') {
    const command = str('command') ?? ''
    const tail = /--detach\b/.test(command) ? '，放到后台跑' : ''
    for (const [pattern, sentence] of CLI_SENTENCE) if (pattern.test(command)) return sentence + tail
    return '运行了一条命令'
  }
  const path = str('file_path') ?? str('path')
  const name = path ? path.split('/').filter(Boolean).slice(-2).join('/') : null
  if (tool === 'Read') return name ? `读了 ${name}` : '读了一个文件'
  if (tool === 'Write') return name ? `写了 ${name}` : '写了一个文件'
  if (tool === 'Edit') return name ? `改了 ${name}` : '改了一个文件'
  if (tool === 'Grep' || tool === 'Glob') return '搜了文件'
  if (tool === 'WebSearch' || tool === 'WebFetch') return '查了网页'
  return `用了 ${tool}`
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/** 被拒的命令，原因翻成一句话；不是认识的拒绝原因就原样给。 */
export function denialSentence(text: string): string {
  if (/Permission to use \w+ has been denied/.test(text)) {
    return '这条命令不在放行范围里。助理只能运行 ai4sci 开头的命令，读写也只限任务包、实验和工作流目录。'
  }
  return text
}
