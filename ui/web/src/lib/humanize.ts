// 把框架的状态码、判决、命令翻成研究者看得懂的短句。页面正文只许用这里的输出；
// 原始值（状态码、哈希、命令）只在展开层出现。字要少：一句话一件事（主人 2026-09-18）。纯函数，有单测。

import type { OutputBrief, RequirementState, Waiting, WorkspaceSummary } from '@/api/types'

// ── 需求与工作区走到哪 ───────────────────────────────────────────────────
/** 需求的状态一句话：未确认 / v2 / v2 · 有改动 */
export function requirementWord(state: RequirementState): string {
  if (!state.confirmed) return '需求未确认'
  return state.dirty ? `需求 v${state.version} · 有改动` : `需求 v${state.version}`
}

/** 页眉里的一句：需求没确认就说需求；有作业就说几个运行中；否则不说（在等谁写在流那一行）。 */
export function stageSentence(w: WorkspaceSummary): string | null {
  if (!w.requirement.confirmed) return requirementWord(w.requirement)
  if (w.running > 0) return `运行中 ${w.running}`
  return null
}

// ── 产出 ────────────────────────────────────────────────────────────────
/** 谁产的：能力名翻成人话，助理 / 人照写 */
export const BY_WORD: Record<string, string> = {
  assistant: '助理', human: '研究者', design: '设计', 'auto-research': '实验', analysis: '分析', verify: '验证',
}

export function byWord(by: string): string {
  return BY_WORD[by] ?? by
}

/** 一次产出的状态一个词 */
export function outputWord(o: Pick<OutputBrief, 'status' | 'signed'>): string {
  if (o.status === 'running') return '运行中'
  if (o.status === 'failed') return '失败'
  if (o.signed === null) return '完成'
  return o.signed.stale ? '已确认 · 之后有改动' : '已确认'
}

/** 流在等谁 */
export const WAITING_WORD: Record<Waiting, string> = {
  job: '运行中', sign: '待确认', assistant: '助理', done: '完成',
}

// ── 实验 ────────────────────────────────────────────────────────────────
export const STOP_SENTENCE: Record<string, string> = {
  patience: '多轮无进步，已停止',
  max_iterations: '轮数用尽',
  max_cost_usd: '预算用尽',
  unrecoverable: '同类错误连续出现，已停止',
  batch_exhausted: '本批完成，可继续',
}

export function stopSentence(reason: string | null, running: boolean): string {
  if (running) return '运行中'
  if (!reason) return '可继续'
  return STOP_SENTENCE[reason] ?? `已停止：${reason}`
}

/** 从 analysis.md 里抽「结论」一节；没有就退回全文。 */
export function conclusionOf(analysis: string): string {
  const match = /^##\s*结论\s*\n([\s\S]*?)(?=^##\s|\s*$)/m.exec(analysis)
  return (match ? match[1] : analysis).trim()
}

// ── 对话里框架来叫醒的那一轮 ──────────────────────────────────────────────
/** 框架来叫醒助理的那一轮，页面上只显示一句：后台作业完成 / 失败 + 那条命令。 */
export function wakeSentence(message: string): string {
  const first = message.split('\n')[0]
  const found = /^作业 \S+（`([^`]+)`）(跑完了|没跑成)/.exec(first)
  if (!found) return first.replace(/`/g, '').slice(0, 80)
  return `后台作业${found[2] === '跑完了' ? '完成' : '失败'}：${found[1]}`
}

/** 被拒的命令，原因翻成一句话；不是认识的拒绝原因就原样给。 */
export function denialSentence(text: string): string {
  if (/Permission to use \w+ has been denied/.test(text)) {
    return '命令不在放行范围'
  }
  return text
}
