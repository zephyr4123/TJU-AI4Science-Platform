import { describe, expect, it } from 'vitest'

import type { OutputBrief, WorkspaceDetail } from '@/api/types'

import { ancestors, fileKind, meaningOf, orderRoot, outputIdOf, parseTable, referencedIds } from './derive'

const out = (id: string, from: string[] = [], signed = false, stale = false): OutputBrief => ({
  id, stage: id.split('/')[0], title: 't', status: 'ok', by: 'design', from, params: {}, flow: null, step: null,
  requirement: 1, chat_id: null, created_at: 't', finished_at: null, result: '', error: '',
  signed: signed ? { by: 'x', signed_at: 't', sha256: 's', note: '', stale } : null,
})

const doc = {
  stages: [
    { name: '设计', slug: 'design', outputs: [out('design/1', [], true), out('design/2')] },
    { name: '实验', slug: 'experiment', outputs: [out('experiment/1', ['design/1'])] },
    { name: '分析', slug: 'analysis', outputs: [] },
  ],
} as unknown as WorkspaceDetail

describe('树里一行是什么', () => {
  const referenced = referencedIds(doc)
  it('被引用的产出集合', () => {
    expect([...referenced]).toEqual(['design/1'])
  })
  it('路径 → 所属产出', () => {
    expect(outputIdOf('design/1/harness/x.py', doc)).toBe('design/1')
    expect(outputIdOf('design/x/y', doc)).toBeNull()
    expect(outputIdOf('materials/1', doc)).toBeNull()
    expect(outputIdOf('requirement.md', doc)).toBeNull()
  })
  it('阶段目录、产出（冻结看引用或签字）、平台记录、其它', () => {
    expect(meaningOf('design', doc, referenced)).toMatchObject({ kind: 'stage', stage: { name: '设计' } })
    expect(meaningOf('design/1', doc, referenced)).toMatchObject({ kind: 'output', frozen: true })
    expect(meaningOf('design/2', doc, referenced)).toMatchObject({ kind: 'output', frozen: false })
    expect(meaningOf('experiment/1', doc, referenced)).toMatchObject({ kind: 'output', frozen: false })
    expect(meaningOf('.ai4sci', doc, referenced)).toEqual({ kind: 'platform' })
    expect(meaningOf('materials', doc, referenced)).toEqual({ kind: 'plain' })
    expect(meaningOf('design/1/harness', doc, referenced)).toEqual({ kind: 'plain' })
    expect(meaningOf('design/9', doc, referenced)).toEqual({ kind: 'plain' })
  })
})

describe('文件怎么渲染', () => {
  it('按后缀', () => {
    expect(fileKind('analysis.md')).toBe('markdown')
    expect(fileKind('fig/loss.PNG')).toBe('image')
    expect(fileKind('ledger.tsv')).toBe('table')
    expect(fileKind('data.csv')).toBe('table')
    expect(fileKind('scoring.yaml')).toBe('text')
    expect(fileKind('SHA256SUMS')).toBe('text')
  })
  it('csv / tsv 切表，超过上限只数不给', () => {
    expect(parseTable('a,b\n1,2\n\n3,4\n', 'x.csv')).toEqual({ header: ['a', 'b'], rows: [['1', '2'], ['3', '4']], more: 0 })
    expect(parseTable('a\tb\n1\t2\n', 'x.tsv').rows).toEqual([['1', '2']])
    const long = ['h'].concat(Array.from({ length: 250 }, (_, i) => String(i))).join('\n')
    const table = parseTable(long, 'x.csv')
    expect(table.rows.length).toBe(200)
    expect(table.more).toBe(50)
    expect(parseTable('', 'x.csv')).toEqual({ header: [''], rows: [], more: 0 })
  })
  it('祖先路径', () => {
    expect(ancestors('design/1/harness/x.py')).toEqual(['design', 'design/1', 'design/1/harness'])
    expect(ancestors('requirement.md')).toEqual([])
  })
})

describe('根一层的顺序', () => {
  it('需求、原件、流、阶段按顺序、其它、点开头的垫底', () => {
    const entries = ['.ai4sci', 'analysis', 'design', 'experiment', 'flows', 'materials', 'notes', 'requirement.lock', 'requirement.md']
      .map((name) => ({ name, kind: name.includes('.') && !name.startsWith('.') ? 'file' as const : 'dir' as const }))
    expect(orderRoot(entries, doc).map((e) => e.name))
      .toEqual(['requirement.md', 'requirement.lock', 'materials', 'flows', 'design', 'experiment', 'analysis', 'notes', '.ai4sci'])
  })
})
