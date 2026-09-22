// 输入框上那几枚旋钮的状态（外层 #86，P-25）：还没开对话时选哪家（缺省照设置里「助理」那家）、这次改过的模型与深度、
// 助理想着时那个词。项目页正中间的输入框与对话视图里的输入框同一份逻辑。
import { useState } from 'react'

import type { Backend, ChatMeta, Tuning } from '@/api/types'
import { type Pick, shownValue, storedTuning, thinkingWord } from '@/lib/tuning'

export interface TuningState {
  /** 这段对话记着的那家；还没开对话就是门里选的（或设置里缺省的）那家 */
  backendName: string | null
  /** 那家的两枚旋钮清单与新对话用的值 */
  knobs: Backend | null
  tuning: Tuning
  thinking: string
  onTune: (next: Tuning) => void
  /** 还没开对话时换一家：旋钮清单跟着换、这次改过的作废 */
  choose: (name: string) => void
}

export function useTuning(backends: Backend[] | null, current: ChatMeta | null): TuningState {
  const [who, setWho] = useState<string | null>(null)
  const backendName = current?.backend ?? who ?? backends?.find((b) => b.default)?.name ?? null
  const knobs = backends?.find((b) => b.name === backendName) ?? null
  // 输入框上这次改过的旋钮；没碰过就沿用对话上记的，随每条消息发出去
  const [pick, setPick] = useState<Pick>({})
  const tuning = storedTuning(pick, current)
  // 按实际用的深度（记着的，或这家新对话用的）在清单里的位置
  const thinking = thinkingWord(shownValue(tuning.effort, knobs?.effort ?? ''), knobs?.efforts ?? [])
  return { backendName, knobs, tuning, thinking, onTune: setPick, choose: (name) => { setWho(name); setPick({}) } }
}
