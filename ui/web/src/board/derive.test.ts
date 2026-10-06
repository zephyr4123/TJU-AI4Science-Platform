import { describe, expect, it } from 'vitest'

import type { FlowProgress, OutputBrief } from '@/api/types'

import { fileKinds, fold, looseOutputs, needsSign, nextStage, outputLine, outputName, stageState, stateOf, stopState, tookWord, waitingSentence } from './derive'

const out = (id: string, signed = false, stale = false) =>
  ({ id, title: 't', status: 'ok' as const, by: 'design', from: [], signed, signed_stale: stale })

const brief = (id: string, over: Partial<OutputBrief> = {}): OutputBrief => ({
  id, stage: id.split('/')[0], title: 't', status: 'ok', by: 'design', from: [], params: {}, flow: null, step: null, requirement: 1,
  chat_id: null, created_at: '2026-10-05T13:23:00+08:00', finished_at: null, result: '', error: '', signed: null, ...over,
})
const signature = (stale = false) => ({ by: 'u', signed_at: 't', sha256: 'x', note: '', stale })

const flow = (items: FlowProgress['items']): FlowProgress => ({
  name: 'f', title: 'f', summary: '', from: null, stages: [], layout: null, covers: [], remarks: [], problems: [], shipped: false,
  items,
  step: 0, total: items?.length ?? 0, waiting: 'sign', job: null,
})

describe('等人签的产出', () => {
  it('断点管前一个阶段的产出：没签的、签了又改的都在等', () => {
    const f = flow([
      { kind: 'stage', index: 0, stage: '设计', caps: [], outputs: [out('design/1'), out('design/2', true), out('design/3', true, true)] },
      { kind: 'stop', index: 1, note: '核对', outputs: [], signed: false },
      { kind: 'stage', index: 2, stage: '实验', caps: [], outputs: [out('experiment/1')] },
    ])
    expect([...needsSign([f])].sort()).toEqual(['design/1', 'design/3'])
  })
  it('没有断点就没人在等；坏掉的流没有 items', () => {
    expect(needsSign([flow([{ kind: 'stage', index: 0, stage: '设计', caps: [], outputs: [out('design/1')] }])]).size).toBe(0)
    expect(needsSign([{ ...flow(undefined), items: undefined }]).size).toBe(0)
  })
})

describe('流在等谁', () => {
  const nameOf = (slug: string) => ({ design: '设计', experiment: '实验', analysis: '分析' })[slug] ?? slug
  const items: FlowProgress['items'] = [
    { kind: 'stage', index: 0, stage: '设计', caps: [], outputs: [out('design/1', true)] },
    { kind: 'stop', index: 1, note: '核对评分脚本算的是不是你要的数', outputs: [], signed: true },
    { kind: 'stage', index: 2, stage: '实验', caps: [{ cap: 'auto-research', with: {} }], outputs: [] },
    { kind: 'stage', index: 3, stage: '分析', caps: [], outputs: [] },
    { kind: 'stop', index: 4, note: '验收', outputs: [], signed: false },
  ]
  it('下一步是 step 之后第一个阶段；走完了是 null', () => {
    expect(nextStage({ ...flow(items), step: 0 })?.stage).toBe('实验')
    expect(nextStage({ ...flow(items), step: 3 })).toBeNull()
  })
  it('一句话：下一步 / 待确认 / 运行中 / 完成 / 坏了', () => {
    const f = flow(items)
    expect(waitingSentence({ ...f, step: 0, waiting: 'assistant' }, new Set(), nameOf)).toBe('下一步：实验阶段 · 助理')
    expect(waitingSentence({ ...f, step: 0, waiting: 'sign' }, new Set(['design/1']), nameOf)).toBe('待确认：设计阶段第 1 次')
    const job = { job_id: 'j', cap: 'auto-research', stage: 'experiment', argv: [], pid: 1, started_at: 't', status: 'running' as const,
                  effective_status: 'running' as const, finished_at: null, exit_code: null, result: '', chat_id: null, log: '', flow: 'f', output: 'experiment/2' }
    expect(waitingSentence({ ...f, step: 0, waiting: 'job', job }, new Set(), nameOf)).toBe('运行中：实验阶段第 2 次')
    expect(waitingSentence({ ...f, step: 3, waiting: 'done' }, new Set(), nameOf)).toBe('完成')
    expect(waitingSentence({ ...f, problems: ['坏'] }, new Set(), nameOf)).toBe('流程文件有误')
  })
  it('产出的状态词按运行 / 失败 / 待确认 / 已确认 / 完成分；确认之后又改了算完成', () => {
    const pending = new Set(['design/1'])
    expect(stateOf(brief('design/1'), pending)).toBe('pending')
    expect(stateOf(brief('design/2', { signed: signature() }), pending)).toBe('confirmed')
    expect(stateOf(brief('design/3', { signed: signature(true) }), pending)).toBe('done')
    expect(stateOf(brief('design/4', { status: 'failed' }), pending)).toBe('failed')
    expect(stateOf(brief('design/5', { status: 'running' }), pending)).toBe('running')
  })
  it('时间线上的节点：阶段分走过 / 当前 / 没到，断点分已确认 / 待确认 / 没到', () => {
    const f = { ...flow(items), step: 0, waiting: 'assistant' as const }
    const [design, stop, experiment, analysis, accept] = items!
    expect(stageState(design as never, f)).toBe('done')
    expect(stageState(experiment as never, f)).toBe('current')
    expect(stageState(analysis as never, f)).toBe('todo')
    expect(stageState(analysis as never, { ...f, step: 3, waiting: 'done' })).toBe('done')
    expect(stopState(stop as never, f)).toBe('signed')
    expect(stopState(accept as never, { ...f, step: 3, waiting: 'sign' })).toBe('pending')
    expect(stopState(accept as never, f)).toBe('todo')
  })
})

describe('产出叫什么', () => {
  const nameOf = (slug: string) => ({ literature: '文献', analysis: '分析' })[slug] ?? slug
  it('阶段名说全、第几次说全；别的工作区的带上那个工作区的名字', () => {
    expect(outputName('literature/3', nameOf)).toBe('文献阶段第 3 次')
    expect(outputName('gua:analysis/1', nameOf, () => '复现 GUA')).toBe('「复现 GUA」的分析阶段第 1 次')
    expect(outputName('gua:analysis/1', nameOf)).toBe('另一个工作区的分析阶段第 1 次')
  })
})

describe('流程外的产出', () => {
  it('没被任何一条流程收下的都在这里：没记流程的、记了流程却没记第几步的；按阶段、再按第几次排', () => {
    const stages = [
      { name: '文献', slug: 'literature', outputs: [brief('literature/1', { flow: 'f', step: 0 }), brief('literature/2', { flow: 'f' }),
                                                     brief('literature/10'), brief('literature/3')] },
      { name: '设计', slug: 'design', outputs: [brief('design/1')] },
    ]
    const f = flow([{ kind: 'stage', index: 0, stage: '文献', caps: [], outputs: [out('literature/1')] }])
    expect(looseOutputs(stages, [f]).map((o) => o.id)).toEqual(['literature/2', 'literature/3', 'literature/10', 'design/1'])
    expect(looseOutputs(stages, []).map((o) => o.id)).toEqual(['literature/1', 'literature/2', 'literature/3', 'literature/10', 'design/1'])
  })
})

describe('一个阶段的产出多了折起来', () => {
  it('新的在前、露两次；待确认与运行中的总露着；折起的数一下有几次失败', () => {
    const outputs = [1, 2, 3, 4, 5].map((n) => brief(`verification/${n}`, { status: n === 2 || n === 3 ? 'failed' : 'ok' }))
    const folded = fold(outputs, new Set(['verification/1']))
    expect(folded.shown.map((o) => o.id)).toEqual(['verification/5', 'verification/4', 'verification/1'])
    expect(folded.hidden.map((o) => o.id)).toEqual(['verification/3', 'verification/2'])
    expect(folded.failed).toBe(2)
    expect(fold(outputs.slice(0, 2), new Set()).hidden).toEqual([])
  })
})

describe('产出悬浮窗里的记录', () => {
  it('文件按种类数：从多到少；一样多照文档、数据、图片、PDF、代码排，其它垫底', () => {
    const paths = ['sources.md', 'seeds.md', 'candidates.jsonl', 'papers/W1/source.pdf', 'papers/W1/structured.json',
      'papers/W1/images/a.png', 'papers/W1/images/b.png', 'papers/W1/images/c.png', 'run.log']
    expect(fileKinds(paths)).toEqual([['图片', 3], ['文档', 2], ['数据', 2], ['PDF', 1], ['其它', 1]])
    expect(fileKinds(['notes/1/note.md', 'notes/2/note.md'])).toEqual([['文档', 2]])
    expect(fileKinds([])).toEqual([])
  })
  it('用时：不到一分钟、几分钟、几小时几分', () => {
    expect(tookWord('2026-10-05T13:23:00+08:00', '2026-10-05T13:23:40+08:00')).toBe('不到 1 分钟')
    expect(tookWord('2026-10-05T13:23:00+08:00', '2026-10-05T13:32:30+08:00')).toBe('9 分钟')
    expect(tookWord('2026-10-05T13:23:00+08:00', '2026-10-05T20:20:00+08:00')).toBe('6 小时 57 分钟')
    expect(tookWord('2026-10-05T13:00:00+08:00', '2026-10-05T15:00:00+08:00')).toBe('2 小时')
  })
  it('标题下那一行把阶段与第几次说全', () => {
    expect(outputLine('literature/3', () => '文献')).toBe('文献阶段 · 第 3 次产出')
  })
})
