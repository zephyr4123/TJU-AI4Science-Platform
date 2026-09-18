// 脊柱上每一项长什么样，全由盘上的状态算出来：run 的便条（flow）、作业、发布 / 验收的记录、任务包的阶段。
// 纯函数，不碰 React；页面「装什么流长什么样」靠它，不写死任何一条流（外层 #58 #64 #98）。
// 房间之间不接管子（P-18），所以这里也不推"下一间要什么"：只回答每一项是做完了、跑着、轮到助理、还是等人。
import type { FlowItem, FlowState, RunSummary, TaskSummary } from '@/api/types'

export type ItemState = 'done' | 'running' | 'assistant' | 'wait-key' | 'wait-human' | 'todo'

export interface ItemView {
  n: number
  item: FlowItem
  state: ItemState
}

/** 便条说「在等谁」时，下一项该亮成什么 */
function openState(waiting: string, item: FlowItem): ItemState {
  if (waiting.startsWith('job:')) return 'running'
  if (waiting.startsWith('key:')) return 'wait-key'
  if (waiting === 'human') return 'wait-human'
  return item.kind === 'stop' ? (item.key ? 'wait-key' : 'wait-human') : 'assistant'
}

/** run 照的那条流：便条说走到第几项、在等谁；验收那一项看记录（便条不会替人的确认推进）。 */
export function deriveRunItems(flow: FlowState, run: Pick<RunSummary, 'accept'>): ItemView[] {
  const accepted = run.accept !== null && !run.accept.stale
  return flow.rooms.map((item, i) => {
    const n = i + 1
    if (item.kind === 'stop' && item.key === 'accept' && accepted) return { n, item, state: 'done' }
    if (n <= flow.step) return { n, item, state: 'done' }
    if (n !== flow.step + 1) return { n, item, state: 'todo' }
    return { n, item, state: openState(flow.waiting, item) }
  })
}

/** 任务包这一段的房间：页面从任务包的阶段推——假设间做完 = 需求填好了，设计间做完 = 基线跑了。
 *  只有这两间能从任务包看出来；别的房间要等 run 才知道。 */
const TASK_ROOMS = new Set(['假设', '设计'])

/** 一条流里属于任务包的那一段：开头连续的假设 / 设计间与它们之间的断点，到第一间别的房间为止。 */
export function taskPart(items: FlowItem[]): FlowItem[] {
  const end = items.findIndex((it) => it.kind === 'room' && !TASK_ROOMS.has(it.stage))
  return end < 0 ? items : items.slice(0, end)
}

/** 还没有 run 的工作区：脊柱就是任务包这一段，状态从任务包的阶段与发布记录推。 */
export function deriveTaskItems(items: FlowItem[], task: TaskSummary | null,
                                problems: string[] | null): ItemView[] {
  const stage = task?.stage ?? null
  const rank = stage === null ? -1 : ['drafting', 'published', 'designed', 'baselined'].indexOf(stage)
  const filled = task !== null && problems !== null && problems.length === 0
  const published = task?.publish.ok === true
  const doneOf = (item: FlowItem): boolean | null => {
    if (item.kind === 'room') {
      if (item.stage === '假设') return filled
      if (item.stage === '设计') return rank >= 3
      return null // 别的房间从任务包看不出来
    }
    if (item.key === 'publish') return published
    return null // 别的断点：跟着它后面那一间走
  }
  const done = items.map(doneOf)
  // 断点做没做完看它后面那一项（人点了头助理才会进下一间）；末尾的断点没人能替它说做完了
  for (let i = items.length - 1; i >= 0; i -= 1) {
    if (done[i] === null && items[i].kind === 'stop') done[i] = i + 1 < items.length ? done[i + 1] : false
  }
  let firstOpen = true // 第一个没完成的项才是「轮到谁」，后面的都是 todo
  return items.map((item, i) => {
    const n = i + 1
    if (done[i]) return { n, item, state: 'done' }
    if (!firstOpen) return { n, item, state: 'todo' }
    firstOpen = false
    if (item.kind === 'stop') return { n, item, state: item.key ? 'wait-key' : 'wait-human' }
    return { n, item, state: 'assistant' }
  })
}

/** 没照流的老 run：按库里的样板从文件推一条便条出来，让它也有脊柱。 */
export function synthesizeFlow(run: RunSummary, items: FlowItem[], name: string, title: string): FlowState {
  const accepted = run.accept !== null && !run.accept.stale
  const roomDone: Record<string, boolean> = {
    假设: true, 设计: true, // 有 run 就说明任务包早就走完了
    实验: run.last_iter > 0, 分析: run.analysis, 验证: run.verify !== null && run.verify.status !== 'invalid',
  }
  let step = 0
  for (const [i, item] of items.entries()) {
    const ok = item.kind === 'room' ? (roomDone[item.stage] ?? false)
      : item.key === 'accept' ? accepted : item.key === 'publish' ? true
      : (items[i + 1]?.kind === 'room' ? (roomDone[(items[i + 1] as { stage: string }).stage] ?? false) : false)
    if (!ok) break
    step = i + 1
  }
  const following = items[step] ?? null
  const waiting = run.job ? `job:${run.job.job_id}` : following === null ? 'done'
    : following.kind === 'stop' ? (following.key ? `key:${following.key}` : 'human') : 'assistant'
  return { workflow: name, title, step, total: items.length, rooms: items, next: following, waiting,
           updated_at: run.updated_at }
}

/** 脊柱标题下那句话：走到哪、在等谁。 */
export function waitingSentence(items: ItemView[], titleOf: (cap: string) => string | undefined): string {
  const open = items.find((s) => s.state !== 'done' && s.state !== 'todo')
  if (!open) return items.length > 0 && items.every((s) => s.state === 'done') ? '走完了' : ''
  const item = open.item
  if (item.kind === 'stop') {
    if (item.key === 'publish') return '等你发布'
    if (item.key === 'accept') return '等你验收'
    return item.note ? `等你确认：${item.note}` : '等你确认'
  }
  const name = item.caps.length ? item.caps.map((c) => titleOf(c.cap) ?? c.cap).join('、') : `${item.stage}间`
  return open.state === 'running' ? `${name}跑着` : `${name}，轮到助理`
}
