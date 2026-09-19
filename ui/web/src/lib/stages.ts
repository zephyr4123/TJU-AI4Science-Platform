// 能力清单按七个研究阶段分组。阶段顺序来自 `GET /stages`，空着的阶段也要占一格：
// 页面诚实地告诉人"这个阶段还没有能力"，比把五颗能力排成一列更能看出平台现在能做到哪。

import type { Capability, ResearchStage } from '@/api/types'

export interface StageGroup {
  stage: ResearchStage
  caps: Capability[]
}

/** 按后端给的阶段顺序分组；描述符里出现了清单外的阶段就追加在末尾，不丢。 */
export function groupByStage(stages: ResearchStage[], caps: Capability[]): StageGroup[] {
  const order = [...stages]
  for (const cap of caps) if (!order.includes(cap.stage)) order.push(cap.stage)
  return order.map((stage) => ({ stage, caps: caps.filter((c) => c.stage === stage) }))
}

/** 一条流程经过哪几个阶段：「假设 → 设计 → 实验」。 */
export function coverageSentence(covers: ResearchStage[]): string {
  return covers.length === 0 ? '没有阶段' : covers.join(' → ')
}

// ── 图标：七个阶段各一枚（Phosphor，全站一套） ──
import { Books, ChartLineUp, Flask, type Icon, Lightbulb, PenNib, PencilRuler, SealCheck } from '@phosphor-icons/react'

/** 阶段名是后端给的中文；清单外的阶段用锥形瓶兜底 */
export const STAGE_ICON: Record<string, Icon> = {
  文献: Books, 假设: Lightbulb, 设计: PencilRuler, 实验: Flask, 分析: ChartLineUp, 写作: PenNib, 验证: SealCheck,
}

export function stageIcon(stage: ResearchStage): Icon {
  return STAGE_ICON[stage] ?? Flask
}
