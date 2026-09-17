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
