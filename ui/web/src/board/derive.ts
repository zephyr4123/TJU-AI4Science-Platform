// 看板上算出来的东西，纯函数、有单测：哪些产出在等人签（流里那一项后面是断点、产出还没签）。
import type { FlowProgress } from '@/api/types'

/** 哪些产出在等人签：流里那一项后面是断点、产出还没签 */
export function needsSign(flows: FlowProgress[]): Set<string> {
  const found = new Set<string>()
  for (const flow of flows) {
    const items = flow.items ?? []
    items.forEach((item, i) => {
      if (item.kind !== 'stop') return
      const previous = [...items.slice(0, i)].reverse().find((it) => it.kind === 'stage')
      for (const o of previous?.outputs ?? []) if (o.status === 'ok' && !(o.signed && !o.signed_stale)) found.add(o.id)
    })
  }
  return found
}

