// 七个研究阶段在页面上的两样小东西：一条流程经过哪几个阶段的那句话、每个阶段的图标。阶段顺序来自 `GET /stages`；
// 能力镜头怎么按阶段摆在 `studio/model.ts`（shelfRows）。

import type { ResearchStage } from '@/api/types'

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
