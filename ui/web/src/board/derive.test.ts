import { describe, expect, it } from 'vitest'

import type { FlowProgress } from '@/api/types'

import { needsSign, nextStage, outputState, shortNote, waitingSentence } from './derive'

const out = (id: string, signed = false, stale = false) =>
  ({ id, title: 't', status: 'ok' as const, by: 'design', from: [], signed, signed_stale: stale })

const flow = (items: FlowProgress['items']): FlowProgress => ({
  name: 'f', title: 'f', summary: '', stages: [], layout: null, covers: [], remarks: [], problems: [], shipped: false, items,
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
    expect(waitingSentence({ ...f, step: 0, waiting: 'assistant' }, new Set(), nameOf)).toBe('下一步：实验 · 助理')
    expect(waitingSentence({ ...f, step: 0, waiting: 'sign' }, new Set(['design/1']), nameOf)).toBe('待确认：设计 · 1')
    const job = { job_id: 'j', cap: 'auto-research', stage: 'experiment', argv: [], pid: 1, started_at: 't', status: 'running' as const,
                  effective_status: 'running' as const, finished_at: null, exit_code: null, result: '', chat_id: null, log: '', flow: 'f', output: 'experiment/2' }
    expect(waitingSentence({ ...f, step: 0, waiting: 'job', job }, new Set(), nameOf)).toBe('运行中：实验 · 2')
    expect(waitingSentence({ ...f, step: 3, waiting: 'done' }, new Set(), nameOf)).toBe('完成')
    expect(waitingSentence({ ...f, problems: ['坏'] }, new Set(), nameOf)).toBe('流程文件有误')
  })
  it('产出的状态词按运行 / 失败 / 待确认 / 已确认 / 完成分', () => {
    const pending = new Set(['design/1'])
    expect(outputState(out('design/1'), pending)).toBe('pending')
    expect(outputState(out('design/2', true), pending)).toBe('confirmed')
    expect(outputState(out('design/3', true, true), pending)).toBe('done')
    expect(outputState({ ...out('design/4'), status: 'failed' }, pending)).toBe('failed')
    expect(outputState({ ...out('design/5'), status: 'running' }, pending)).toBe('running')
  })
  it('断点的短标签：第一段、最多六个字', () => {
    expect(shortNote('核对评分脚本算的是不是你要的数')).toBe('核对评分脚本')
    expect(shortNote('验收')).toBe('验收')
    expect(shortNote('看一眼，别急')).toBe('看一眼')
    expect(shortNote('')).toBe('')
  })
})
