import { describe, expect, it } from 'vitest'

import type { Workflow } from '@/api/types'

import {
  fromWorkflow, indexAt, insertAt, layout, moveTo, parseParam, problemIndices, ROW_PITCH, ROW_WIDTH, setParam, stageItem, stopItem,
  toDraft, toggleCap, WIDTH,
} from './model'

const strip = (draft: ReturnType<typeof fromWorkflow>) => draft.items.map((it) => (it.kind === 'stop' ? { note: it.note } : { stage: it.stage, caps: it.caps }))

describe('画布 ↔ 文件', () => {
  it('不点名一个名字、点名一个清单、带参数写映射、断点一个词或一句话', () => {
    const draft = {
      name: ' r ', title: 't', summary: 's',
      items: [
        stageItem('假设'), stopItem('发布'),
        stageItem('设计', [{ cap: 'design', with: {} }]),
        stopItem(''),
        stageItem('实验', [{ cap: 'auto-research', with: { max_iters: 3 } }, { cap: 'x', with: {} }]),
      ],
    }
    expect(toDraft(draft)).toEqual({
      name: 'r', title: 't', summary: 's',
      stages: ['假设', { 断点: '发布' }, { 设计: ['design'] }, '断点', { 实验: { 'auto-research': { max_iters: 3 }, x: null } }],
    })
  })
  it('库里的一条载入画布时参数跟着来，名字照旧', () => {
    const wf = {
      name: 'research', title: 't', summary: 's', covers: [], remarks: [], problems: [],
      stages: [
        { kind: 'stage', stage: '实验', caps: [{ cap: 'auto-research', with: { max_iters: 3 } }] },
        { kind: 'stop', key: 'accept', note: '验收' },
      ],
    } as Workflow
    const draft = fromWorkflow(wf)
    expect(draft.name).toBe('research')
    expect(strip(draft)).toEqual([{ stage: '实验', caps: [{ cap: 'auto-research', with: { max_iters: 3 } }] }, { note: '验收' }])
  })
})

describe('排版与拖放', () => {
  const items = [stageItem('假设'), stopItem('发布'), stageItem('设计')]
  it('一行从左到右，断点窄', () => {
    const slots = layout(items)
    expect(slots.map((s) => s.width)).toEqual([WIDTH.stage, WIDTH.stop, WIDTH.stage])
    expect(slots[1].x).toBeGreaterThan(slots[0].x + WIDTH.stage)
    expect(slots.every((s) => s.row === 0)).toBe(true)
  })
  it('一行放不下就换行：出厂那条 8 项分两行', () => {
    const research = [stageItem('假设'), stopItem('发布'), stageItem('设计'), stopItem('核对'), stageItem('实验'), stageItem('分析'), stageItem('验证'), stopItem('验收')]
    const slots = layout(research)
    expect(slots.map((s) => s.row)).toEqual([0, 0, 0, 0, 1, 1, 1, 1])
    expect(slots[4]).toMatchObject({ x: 0, y: ROW_PITCH })
    expect(Math.max(...slots.map((s) => s.x + s.width))).toBeLessThanOrEqual(ROW_WIDTH)
  })
  it('落点在哪几项的中点右边，就插在它们后面；落在下一行就排到末尾', () => {
    expect(indexAt(items, -10, 0)).toBe(0)
    expect(indexAt(items, WIDTH.stage / 2 + 1, 0)).toBe(1)
    expect(indexAt(items, 10_000, 0)).toBe(3)
    expect(indexAt(items, 0, ROW_PITCH)).toBe(3)
    expect(insertAt(items, 1, stopItem('x')).map((it) => it.kind)).toEqual(['stage', 'stop', 'stop', 'stage'])
  })
  it('拖一个节点到最右边，它就排到最后；拖回原处顺序不变', () => {
    const moved = moveTo(items, items[0].uid, 10_000, 0)
    expect(moved.map((it) => it.uid)).toEqual([items[1].uid, items[2].uid, items[0].uid])
    expect(moveTo(items, items[0].uid, 0, 0).map((it) => it.uid)).toEqual(items.map((it) => it.uid))
  })
})

describe('节点里的能力与参数', () => {
  it('勾上加一颗、去掉连参数一起走；重复勾不变', () => {
    const a = toggleCap(stageItem('实验'), 'auto-research', true)
    expect(a.caps).toEqual([{ cap: 'auto-research', with: {} }])
    expect(toggleCap(a, 'auto-research', true)).toBe(a)
    const b = setParam(a, 'auto-research', 'max_iters', 3)
    expect(b.caps[0].with).toEqual({ max_iters: 3 })
    expect(setParam(b, 'auto-research', 'max_iters', undefined).caps[0].with).toEqual({})
    expect(toggleCap(b, 'auto-research', false).caps).toEqual([])
  })
  it('输入框的字按类型解析：空与坏值都清掉', () => {
    expect(parseParam('int', '3')).toBe(3)
    expect(parseParam('int', '3.5')).toBeUndefined()
    expect(parseParam('float', '0.01')).toBe(0.01)
    expect(parseParam('float', 'abc')).toBeUndefined()
    expect(parseParam('str', ' a ')).toBe('a')
    expect(parseParam('str', '')).toBeUndefined()
  })
  it('后端的问题句点到「第 N 项」就贴到第 N 个节点，点到两项贴两个', () => {
    expect(problemIndices('第 3 项「设计」里的 verify 属于「验证」阶段')).toEqual([2])
    expect(problemIndices('第 2 项与第 3 项都是断点：两个断点挨着等于一个')).toEqual([1, 2])
    expect(problemIndices('有实验没有验证')).toEqual([])
  })
})
