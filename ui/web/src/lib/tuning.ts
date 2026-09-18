// 输入框上两枚旋钮的取值规则（外层 #86）。三层：这次改过的 > 这段对话记着的 > 后端缺省。
// 发出去、记进对话的只有前两层——后端缺省不抄成明选，换了环境里的缺省老对话也跟着换。
import type { Tuning } from '@/api/types'

/** 字段缺席 = 这次没碰过那枚旋钮 */
export type Pick = Partial<Tuning>

/** 发出去并记进对话的值：这次改过的压过对话上记的；都没有就是 null（后端缺省） */
export function storedTuning(pick: Pick, meta: Tuning | null): Tuning {
  return {
    model: pick.model !== undefined ? pick.model : meta?.model ?? null,
    effort: pick.effort !== undefined ? pick.effort : meta?.effort ?? null,
  }
}

/** 旋钮上显示哪一格：记着的 > 后端缺省 > ''（写「默认」，CLI 自己定、页面不猜） */
export function shownValue(stored: string | null, fallback: string | null): string {
  return stored ?? fallback ?? ''
}
