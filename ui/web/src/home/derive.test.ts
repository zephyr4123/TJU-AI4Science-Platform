import { describe, expect, it } from 'vitest'

import type { ProjectSummary } from '@/api/types'

import { findProjects, marks, newestFirst, wordsOf } from './derive'

const project = (over: Partial<ProjectSummary> = {}): ProjectSummary => ({
  id: 'p', title: '复现 GUA：Gradient-Update Alignment', goal: '', root: '/x', created_at: '2026-09-22T10:00:00+08:00',
  workspaces: 1, running: 0, ...over,
})

describe('首页的项目清单', () => {
  it('新建的在前', () => {
    const old = project({ id: 'old', created_at: '2026-09-22T10:00:00+08:00' })
    const fresh = project({ id: 'new', created_at: '2026-10-05T10:00:00+08:00' })
    expect(newestFirst([old, fresh]).map((p) => p.id)).toEqual(['new', 'old'])
  })
  it('搜索看名字和目标，不分大小写；空白不算词', () => {
    const gua = project({ id: 'gua' })
    const memory = project({ id: 'mem', title: '大模型智能体的长期记忆', goal: '先摸清近两年这方面的研究都在做什么' })
    const all = [gua, memory]
    expect(findProjects(all, '').map((p) => p.id)).toEqual(['gua', 'mem'])
    expect(findProjects(all, '   ').map((p) => p.id)).toEqual(['gua', 'mem'])
    expect(findProjects(all, 'gradient').map((p) => p.id)).toEqual(['gua'])
    expect(findProjects(all, '研究').map((p) => p.id)).toEqual(['mem'])
  })
  it('几个词都要对上，不论先后', () => {
    const all = [project({ id: 'gua' }), project({ id: 'pinn', title: '复现一篇 PINN 训练方法的论文' })]
    expect(findProjects(all, 'alignment 复现').map((p) => p.id)).toEqual(['gua'])
    expect(findProjects(all, '复现 论文').map((p) => p.id)).toEqual(['pinn'])
    expect(findProjects(all, '复现 没有这个词')).toEqual([])
  })
  it('搜中的几段标出来：重叠的并成一段，不分大小写，原文大小写不变', () => {
    expect(marks('复现 GUA：Gradient-Update', wordsOf('gua 复'))).toEqual([
      { text: '复', hit: true }, { text: '现 ', hit: false }, { text: 'GUA', hit: true }, { text: '：Gradient-Update', hit: false },
    ])
    expect(marks('PINNs 复现', wordsOf('pin pinn'))).toEqual([{ text: 'PINN', hit: true }, { text: 's 复现', hit: false }])
    expect(marks('没搜', [])).toEqual([{ text: '没搜', hit: false }])
  })
})
