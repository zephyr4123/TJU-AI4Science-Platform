import { describe, expect, it } from 'vitest'

import type { SkillEntry, Workflow } from '@/api/types'

import {
  append, autoLayout, byFamily, deriveFrom, dropAt, fromWorkflow, groupSkills, hoverLine, inFamily, indexAt, insertAt, lineageLine, parseParam,
  place, positions, problemIndices, ROW_PITCH, ROW_WIDTH, setParam, skillsFor, stageItem, stopItem, tidy, toDraft, toggleCap, WIDTH,
} from './model'

const strip = (draft: ReturnType<typeof fromWorkflow>) => draft.items.map((it) => (it.kind === 'stop' ? { note: it.note } : { stage: it.stage, caps: it.caps }))

describe('画布 ↔ 文件', () => {
  it('不点名一个名字、点名一个清单、带参数写映射、断点一个词或一句话', () => {
    const draft = {
      name: ' r ', title: 't', summary: 's', from: null,
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
      name: 'research', title: 't', summary: 's', from: null, covers: [], remarks: [], problems: [], shipped: false, layout: null,
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
    const draft = { name: 'r', title: 't', summary: 's', items, from: null }
    expect(toDraft(draft).layout).toBeUndefined()
    const moved = { ...draft, items: place(items, items[2].uid, { x: 900.4, y: 0 }) }
    expect(toDraft(moved).layout).toEqual([[0, 0], [WIDTH.stage + 56, 0], [900, 0]])
    const wf = { name: 'x', title: 't', summary: 's', from: null, covers: [], remarks: [], problems: [], shipped: false, layout: [[5, 6], [7, 8]],
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

const flow = (name: string, extra: Partial<Workflow> = {}): Workflow => ({
  name, title: name, summary: 's', covers: [], remarks: [], problems: [], shipped: false, layout: null, from: null,
  stages: [{ kind: 'stage', stage: '设计', caps: [] }], family: name, diff: [], parent_changed: false, ...extra,
}) as Workflow

describe('流程的血缘（P-15）', () => {
  it('从出厂的派生：名字空着交给平台起，存的时候只带父流程的名字', () => {
    const draft = deriveFrom(flow('research', { shipped: true }))
    expect(draft.name).toBe('')
    expect(toDraft(draft).from).toBe('research')
  })
  it('改自己存过的：名字与血缘原样带回去', () => {
    const own = flow('research-2', { from: { name: 'research', hash: 'abcdef123456' }, family: 'research' })
    expect(toDraft(fromWorkflow(own))).toMatchObject({ name: 'research-2', from: { name: 'research', hash: 'abcdef123456' } })
    expect(toDraft(fromWorkflow(flow('scratch'))).from).toBeUndefined()
  })
  it('库按家族排：派生的跟在家族的头后面、序号按数字排，父流程不在了的放最后、不缩进', () => {
    const rows = [
      flow('research', { shipped: true }), flow('reproduce', { shipped: true }),
      flow('research-10', { from: { name: 'research-2', hash: 'a'.repeat(12) }, family: 'research' }),
      flow('reproduce-2', { from: { name: 'reproduce', hash: 'b'.repeat(12) }, family: 'reproduce' }),
      flow('research-2', { from: { name: 'research', hash: 'c'.repeat(12) }, family: 'research' }),
      flow('research-9', { from: { name: 'research', hash: 'e'.repeat(12) }, family: 'research' }),
      // 后端真给的孤儿形状：父流程 reproduce-3 删了，家族走不上去，家族名就是它自己
      flow('reproduce-4', { from: { name: 'reproduce-3', hash: 'd'.repeat(12) }, family: 'reproduce-4' }),
    ]
    const sorted = byFamily(rows)
    expect(sorted.map((wf) => wf.name)).toEqual(
      ['research', 'research-2', 'research-9', 'research-10', 'reproduce', 'reproduce-2', 'reproduce-4'])
    expect(sorted.map(inFamily)).toEqual([false, true, true, true, false, true, false])
  })
  it('悬停一行：有问题说问题，派生的说改了什么，别的说说明（差异为空数组不顶掉说明）', () => {
    expect(hoverLine(flow('scratch', { diff: [], summary: '一句说明' }))).toBe('一句说明')
    expect(hoverLine(flow('research-2', { diff: ['去掉断点'], summary: 's' }))).toBe('去掉断点')
    expect(hoverLine({ ...flow('x', { diff: ['去掉断点'] }), problems: ['重名'] })).toBe('重名')
  })
  it('小字一行：派生的写改了什么，父流程改过先说', () => {
    expect(lineageLine(flow('research', { shipped: true }))).toBe('1 项，出厂')
    const child = flow('research-2', { from: { name: 'research', hash: 'a'.repeat(12) }, diff: ['加了阶段「文献」', '去掉断点'] })
    expect(lineageLine(child)).toBe('加了阶段「文献」；去掉断点')
    expect(lineageLine({ ...child, diff: [], parent_changed: true })).toBe('父流程后来改过；与父流程一样')
  })
})

const skill = (name: string, where: string, brief = name): SkillEntry => ({
  name, kind: 'skill', title: name, brief, library: where.startsWith('收录') ? '收录' : where, shelf: '', where,
  scripts: [], used_by: [],
})

describe('skill 怎么摆（P-22、P-26）', () => {
  const lib = [skill('pdf', '平台'), skill('paper-lookup', '收录·文献', '查论文 OpenAlex'), skill('polish', '收录·写作'),
    skill('plot', '收录·通用'), skill('petab', 'petab')]
  it('不查找时：挂上的在前，再是平台自带的与这个阶段那一架的', () => {
    expect(skillsFor(lib, '文献', [], '').map((s) => s.name)).toEqual(['pdf', 'paper-lookup'])
    expect(skillsFor(lib, '文献', ['polish'], '').map((s) => s.name)).toEqual(['polish', 'pdf', 'paper-lookup'])
  })
  it('查找时看全库：词都要有、不分大小写', () => {
    expect(skillsFor(lib, '文献', [], 'openalex').map((s) => s.name)).toEqual(['paper-lookup'])
    expect(skillsFor(lib, '写作', [], 'p').map((s) => s.name)).toEqual(['pdf', 'paper-lookup', 'polish', 'plot', 'petab'])
    expect(skillsFor(lib, '写作', [], '查论文 nope')).toEqual([])
  })
  it('能力镜头按出处分架，照后端给的顺序', () => {
    expect(groupSkills(lib).map((g) => [g.where, g.skills.length])).toEqual(
      [['平台', 1], ['收录·文献', 1], ['收录·写作', 1], ['收录·通用', 1], ['petab', 1]])
  })
})
