// 鼠标停到首页那一行就先去取那个项目的一整份（外层 #250）：点下去时多半已经在了，项目页直接摆出来，不先闪骨架。
// 取回来的记进 lib/lastSeen，项目页的 useResource 用同一个名字先摆它、再在后台重拉。

import { api } from '@/api/client'
import { keep } from '@/lib/lastSeen'

export const projectKey = (id: string) => `project:${id}`

const inFlight = new Set<string>()

export function prefetchProject(id: string): void {
  if (inFlight.has(id)) return
  inFlight.add(id)
  api.project(id)
    .then((doc) => keep(projectKey(id), doc))
    // 预取失败不报：点进去时照常取，错在那里说
    .catch(() => undefined)
    .finally(() => inFlight.delete(id))
}
