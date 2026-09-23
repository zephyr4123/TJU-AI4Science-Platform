// 把框架的状态码、判决、命令翻成研究者看得懂的短句。页面正文只许用这里的输出；
// 原始值（状态码、哈希、命令）只在展开层出现。字要少：一句话一件事（主人 2026-09-18）。纯函数，有单测。

import type { OutputBrief, RequirementState, WorkspaceSummary } from '@/api/types'

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
/** 谁产的：助理 / 研究者手写的照写；能力产的写能力的名（`titleOf` 查后端给的能力表，P-21：页面不自己翻） */
export const BY_WORD: Record<string, string> = { assistant: '助理', human: '研究者' }

export function byWord(by: string, titleOf: (name: string) => string | undefined): string {
  return BY_WORD[by] ?? titleOf(by) ?? by
}

/** 一次产出的状态一个词 */
export function outputWord(o: Pick<OutputBrief, 'status' | 'signed'>): string {
  if (o.status === 'running') return '运行中'
  if (o.status === 'failed') return '失败'
  if (o.signed === null) return '完成'
  return o.signed.stale ? '已确认 · 之后有改动' : '已确认'
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
