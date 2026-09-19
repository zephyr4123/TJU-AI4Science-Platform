// 把框架的状态码、判决、命令翻成研究者看得懂的短句。页面正文只许用这里的输出；
// 原始值（状态码、哈希、命令）只在展开层出现。字要少：一句话一件事（主人 2026-09-18）。纯函数，有单测。

import type { OutputBrief, RequirementState, Waiting, WorkspaceSummary } from '@/api/types'

// ── 需求与工作区走到哪 ───────────────────────────────────────────────────
/** 需求的状态一句话：未确认 / v2 / v2，改了 */
export function requirementWord(state: RequirementState): string {
  if (!state.confirmed) return '需求未确认'
  return state.dirty ? `需求 v${state.version}，改了` : `需求 v${state.version}`
}

/** 页眉里说这个工作区走到哪：需求没确认就说需求；确认了就数产出。 */
export function stageSentence(w: WorkspaceSummary): string {
  if (!w.requirement.confirmed) return requirementWord(w.requirement)
  const total = Object.values(w.counts).reduce((a, b) => a + b, 0)
  if (w.running > 0) return `${w.running} 个作业在跑`
  return total === 0 ? '还没开工' : `${total} 次产出`
}

// ── 产出 ────────────────────────────────────────────────────────────────
/** 谁产的：能力名翻成人话，助理 / 人照写 */
export const BY_WORD: Record<string, string> = {
  assistant: '助理', human: '你', design: '评分脚本', 'auto-research': '实验', analysis: '分析', verify: '核对',
}

export function byWord(by: string): string {
  return BY_WORD[by] ?? by
}

/** 一次产出的状态一句话 */
export function outputWord(o: Pick<OutputBrief, 'status' | 'signed'>): string {
  if (o.status === 'running') return '在做'
  if (o.status === 'failed') return '没成'
  if (o.signed === null) return '成了'
  return o.signed.stale ? '签过，之后改了' : '签过'
}

/** 流在等谁 */
export const WAITING_WORD: Record<Waiting, string> = {
  job: '作业在跑', sign: '等你签', assistant: '轮到助理', done: '走完了',
}

// ── 实验 ────────────────────────────────────────────────────────────────
export const STOP_SENTENCE: Record<string, string> = {
  patience: '几轮没进步，停了',
  max_iterations: '轮数用完',
  max_cost_usd: '花费到顶',
  unrecoverable: '同一种错连着出，停了',
  batch_exhausted: '这批跑完，可再跑',
}

export function stopSentence(reason: string | null, running: boolean): string {
  if (running) return '在跑'
  if (!reason) return '可继续'
  return STOP_SENTENCE[reason] ?? `停了：${reason}`
}

/** 从 analysis.md 里抽「结论」一节；没有就退回全文。 */
export function conclusionOf(analysis: string): string {
  const match = /^##\s*结论\s*\n([\s\S]*?)(?=^##\s|\s*$)/m.exec(analysis)
  return (match ? match[1] : analysis).trim()
}

// ── 对话里的工具行 ────────────────────────────────────────────────────────
// 每条命令一句直白的话：查了什么、运行了什么、写了什么。带 --detach 的加一句「放到后台跑」。
const CLI_SENTENCE: [RegExp, string][] = [
  [/ai4sci cap design/, '写了评分脚本、跑了基线'],
  [/ai4sci cap auto-research.*--resume/, '接着跑上次没走完的实验'],
  [/ai4sci cap auto-research.*--(patience|max-iterations|max-cost-usd)/, '给实验续了命，接着跑'],
  [/ai4sci cap auto-research/, '跑了几轮实验'],
  [/ai4sci cap analysis/, '写了分析初稿'],
  [/ai4sci cap verify/, '核对了分析里的数字'],
  [/ai4sci requirement confirm/, '替人确认了需求（该由人确认）'],
  [/ai4sci sign\b/, '替人签了字（该由人签）'],
  [/ai4sci output new/, '开了一次产出'],
  [/ai4sci show workspaces/, '查了有哪些工作区'],
  [/ai4sci show workspace\b/, '看了工作区走到哪'],
  [/ai4sci show outputs?\b/, '看了产出'],
  [/ai4sci show jobs?\b/, '查了后台作业'],
  [/ai4sci show flows\b/, '看了这个工作区里的流'],
  [/ai4sci show caps/, '查了有哪些能力'],
  [/ai4sci show workflows/, '查了库里有哪些流'],
  [/ai4sci show templates?\b/, '看了需求模板'],
  [/ai4sci flow take/, '从库里取了一条流'],
  [/ai4sci workspace new/, '起了一个工作区'],
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

/** 框架来叫醒助理的那一轮，页面上只显示一句：哪件事跑完了或没跑成。 */
export function wakeSentence(message: string): string {
  const first = message.split('\n')[0]
  const found = /^作业 \S+（`([^`]+)`）(跑完了|没跑成)/.exec(first)
  if (!found) return first.replace(/`/g, '').slice(0, 80)
  const what = toolSentence('Bash', { command: found[1] }).replace(/，放到后台跑$/, '')
  return `后台作业${found[2]}（${what}）`
}

/** 被拒的命令，原因翻成一句话；不是认识的拒绝原因就原样给。 */
export function denialSentence(text: string): string {
  if (/Permission to use \w+ has been denied/.test(text)) {
    return '命令不在放行范围'
  }
  return text
}
