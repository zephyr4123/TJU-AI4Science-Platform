// 「助理还不能说话」那扇窗什么时候弹（外层 #282）：只看 `/settings` 的 `assistant`，助理那家此刻的状态。
// 只有缺 key 才弹（填 DeepSeek 的 key）；说不了话（余额不足、连不上）不弹，原因写在设置里——不能把它们当成缺 key；
// 没检查过时页面后台探一次。「跳过」记在本机，记的是跳过时那次自检的时间：下一次自检结果出来才再弹。
// 判据是纯函数，vitest 直接测；读写本机的两个小函数不测。
import type { AssistantStatus } from '@/api/types'

export type KeyPromptStep = 'ask' | 'probe' | 'none'

/** 跳过的是哪一次：那次自检的时间；还没自检过记空串（自检一次、有了时间才再弹） */
export function skipMark(assistant: AssistantStatus): string {
  return assistant.checked_at ?? ''
}

/** 这一刻该做什么：`ask` 弹窗；`probe` 后台探一次（一次页面加载只探一次，探没探过由调用方记）；`none` 什么都不做。
 *  `skipped` 是本机记的跳过，没记是 null；设置还没取到是 null */
export function keyPromptStep(assistant: AssistantStatus | null, skipped: string | null, probed: boolean): KeyPromptStep {
  if (!assistant) return 'none'
  if (assistant.state === 'needs_key') return skipped === skipMark(assistant) ? 'none' : 'ask'
  if (assistant.state === 'unchecked') return probed ? 'none' : 'probe'
  return 'none'
}

const KEY = 'assistant:skipped'

/** 本机记的跳过；没记过、或浏览器不让读（隐私窗口）是 null */
export function storedSkip(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null  // 读不到就当没跳过：多弹一次，不会该弹的不弹
  }
}

export function rememberSkip(mark: string): void {
  try {
    localStorage.setItem(KEY, mark)
  } catch {
    // 记不住（隐私窗口、禁了存储）：这一次照样关窗，下次打开页面再弹
  }
}
