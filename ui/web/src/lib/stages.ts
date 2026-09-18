// 能力清单按七个科研阶段分组。阶段顺序来自 `GET /stages`，空着的阶段也要占一格：
// 页面诚实地告诉人"这一步还没有能力"，比把六颗能力排成一列更能看出平台现在能做到哪。

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

/** 谁来做：要执行层的是助理（agent），不要的是机器，不经过模型。 */
export function actorOf(cap: Pick<Capability, 'needs_executor'>): '助理' | '机器' {
  return cap.needs_executor ? '助理' : '机器'
}

/** 一条流覆盖了哪几段：「设计 → 实验 → 分析」。 */
export function coverageSentence(covers: ResearchStage[]): string {
  return covers.length === 0 ? '不含能力步骤' : `覆盖 ${covers.join(' → ')}`
}

// ── 图标：七段各一枚，两颗键各一枚，人的话与助理的填写各一枚（Phosphor，全站一套） ──
import {
  Books, ChartLineUp, ChatCircleText, Flask, type Icon, Lightbulb, NotePencil, PenNib, PencilRuler, SealCheck,
  Signature, Stamp,
} from '@phosphor-icons/react'

/** 阶段名是后端给的中文；清单外的阶段用锥形瓶兜底 */
export const STAGE_ICON: Record<string, Icon> = {
  文献: Books, 假设: Lightbulb, 设计: PencilRuler, 实验: Flask, 分析: ChartLineUp, 写作: PenNib, 验证: SealCheck,
}

export function stageIcon(stage: ResearchStage): Icon {
  return STAGE_ICON[stage] ?? Flask
}

/** 流里的一步配哪枚：能力按它的阶段，发布键盖章、验收键签名，人开口说话、助理提笔填写 */
export function stepIcon(step: { by: string; cap: string | null; key: string | null },
                         stageOfCap: (cap: string) => ResearchStage | undefined): Icon {
  if (step.key === 'publish') return Stamp
  if (step.key === 'accept') return Signature
  if (step.cap) return stageIcon(stageOfCap(step.cap) ?? '')
  return step.by === '人' ? ChatCircleText : NotePencil
}
