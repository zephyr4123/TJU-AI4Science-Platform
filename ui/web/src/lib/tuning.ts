// 思考深度在页面上的唯一用处：助理想着时输入框里那个词（外层 #86）。哪家、模型、深度只在设置里改（外层 #257）。
import type { Choice } from '@/api/types'

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
