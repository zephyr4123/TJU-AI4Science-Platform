import { describe, expect, it } from 'vitest'

import type { Workflow } from '@/api/types'

import {
  append, autoLayout, dropAt, fromWorkflow, indexAt, insertAt, parseParam, place, positions, problemIndices, ROW_PITCH, ROW_WIDTH,
  setParam, stageItem, stopItem, tidy, toDraft, toggleCap, WIDTH,
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
      name: 'research', title: 't', summary: 's', covers: [], remarks: [], problems: [], shipped: false, layout: null,
      stages: [
        { kind: 'stage', stage: '实验', caps: [{ cap: 'auto-research', with: { max_iters: 3 } }] },
        { kind: 'stop', note: '验收' },
      ],
    } as Workflow
    const draft = fromWorkflow(wf)
    expect(draft.name).toBe('research')
    expect(strip(draft)).toEqual([{ stage: '实验', caps: [{ cap: 'auto-research', with: { max_iters: 3 } }] }, { note: '验收' }])
  })
})

describe('位置与顺序', () => {
  const items = [stageItem('假设'), stopItem('发布'), stageItem('设计')]
  it('没摆过就自动排：一行从左到右，断点窄，放不下换行（出厂那条 8 项分两行）', () => {
    const at = autoLayout(items)
    expect(at.every((p) => p.y === 0)).toBe(true)
    expect(at[1].x).toBe(WIDTH.stage + 56)
    const research = [stageItem('假设'), stopItem('发布'), stageItem('设计'), stopItem('核对'), stageItem('实验'), stageItem('分析'), stageItem('验证'), stopItem('验收')]
    const rows = autoLayout(research).map((p) => p.y / ROW_PITCH)
    expect(rows).toEqual([0, 0, 0, 0, 0, 1, 1, 1])  // 断点只有 56px 宽，第一行放得下五项
    expect(Math.max(...autoLayout(research).map((p, i) => p.x + WIDTH[research[i].kind]))).toBeLessThanOrEqual(ROW_WIDTH)
  })
  it('摆过的按摆的，其余仍自动排；整理后全部回到自动排', () => {
    const moved = place(items, items[2].uid, { x: 900, y: 0 })
    expect(positions(moved)[2]).toEqual({ x: 900, y: 0 })
    expect(positions(moved)[0]).toEqual(autoLayout(moved)[0])
    expect(tidy(moved).every((it) => it.pos === undefined)).toBe(true)
  })
  it('落点在哪几项的中点右边，就插在它们后面；落在下一带就排到末尾', () => {
    expect(indexAt(items, -10, 0)).toBe(0)
    expect(indexAt(items, WIDTH.stage / 2 + 1, 0)).toBe(1)
    expect(indexAt(items, 10_000, 0)).toBe(3)
    expect(indexAt(items, 0, ROW_PITCH)).toBe(3)
    expect(insertAt(items, 1, stopItem('x')).map((it) => it.kind)).toEqual(['stage', 'stop', 'stop', 'stage'])
    const dropped = dropAt(items, { kind: 'stage', stage: '实验' }, 400, 10)
    expect(dropped.map((it) => it.kind)).toEqual(['stage', 'stop', 'stage', 'stage'])
    expect(dropped[2].pos).toEqual({ x: 400 - WIDTH.stage / 2, y: -30 })
  })
  it('拖到最左边就排第一、留在松手处；拖到下一带就排到最后；点一下加到末尾接在最后一项右边', () => {
    const first = place(items, items[2].uid, { x: -300, y: 0 })
    expect(first.map((it) => it.uid)).toEqual([items[2].uid, items[0].uid, items[1].uid])
    expect(first[0].pos).toEqual({ x: -300, y: 0 })
    const down = place(items, items[0].uid, { x: 0, y: ROW_PITCH })
    expect(down.map((it) => it.uid)).toEqual([items[1].uid, items[2].uid, items[0].uid])
    const more = append(first, { kind: 'stop', note: '' })
    expect(more[3].pos).toBeUndefined()
    const more2 = append(place(items, items[2].uid, { x: 900, y: 0 }), { kind: 'stop', note: '' })
    expect(more2[3].pos).toEqual({ x: 900 + WIDTH.stage + 56, y: 0 })
  })
  it('摆过才把坐标写进文件；库里带 layout 的载入时照它摆', () => {
    const draft = { name: 'r', title: 't', summary: 's', items }
    expect(toDraft(draft).layout).toBeUndefined()
    const moved = { ...draft, items: place(items, items[2].uid, { x: 900.4, y: 0 }) }
    expect(toDraft(moved).layout).toEqual([[0, 0], [WIDTH.stage + 56, 0], [900, 0]])
    const wf = { name: 'x', title: 't', summary: 's', covers: [], remarks: [], problems: [], shipped: false, layout: [[5, 6], [7, 8]],
      stages: [{ kind: 'stage', stage: '假设', caps: [] }, { kind: 'stop', note: '' }] } as Workflow
    expect(fromWorkflow(wf).items.map((it) => it.pos)).toEqual([{ x: 5, y: 6 }, { x: 7, y: 8 }])
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
