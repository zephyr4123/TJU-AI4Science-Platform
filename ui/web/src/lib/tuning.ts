// 输入框上两枚旋钮的取值规则（外层 #86，P-25）。这次改过的 > 这段对话记着的 > 这家新对话用的（按人的设置）。
// 旋钮上只有具体值：对话开了就把设置里的值记进 meta，之后各用各的；还没开对话时片上显示设置里的值。
import type { Choice, Tuning } from '@/api/types'

/** 字段缺席 = 这次没碰过那枚旋钮 */
export type Pick = Partial<Tuning>

/** 发出去并记进对话的值：这次改过的压过对话上记的；都没有就是 null（后端缺省） */
export function storedTuning(pick: Pick, meta: Tuning | null): Tuning {
  return {
    model: pick.model !== undefined ? pick.model : meta?.model ?? null,
    effort: pick.effort !== undefined ? pick.effort : meta?.effort ?? null,
  }
}

/** 旋钮上显示哪一格：记着的，或这家新对话用的值 */
export function shownValue(stored: string | null, fallback: string): string {
  return stored ?? fallback
}

/** 助理想着的时候那个词（主人：别用复杂中文，一个英文词，文艺且直白）：按选的深度在清单里的位置，越深越用力；
 * 没选、清单里没有、清单只有一档，都是 thinking */
export function thinkingWord(effort: string, efforts: Choice[]): string {
  const i = efforts.findIndex((c) => c.id === effort)
  if (i < 0 || efforts.length < 2) return 'thinking'
  const depth = i / (efforts.length - 1)
  if (depth === 1) return 'ultra thinking'
  if (depth >= 0.75) return 'deep thinking'
  if (depth >= 0.5) return 'hard thinking'
  return 'thinking'
}
