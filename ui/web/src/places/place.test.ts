import { describe, expect, it } from 'vitest'

import { parseStored, projectOf, worldOf } from './place'

describe('上次在哪', () => {
  it('只认项目与工作区，字段不对就当没记', () => {
    expect(parseStored(null)).toBeNull()
    expect(parseStored('not json')).toBeNull()
    expect(parseStored('"x"')).toBeNull()
    expect(parseStored('{}')).toBeNull()
    expect(parseStored('{"project":"gua"}')).toEqual({ kind: 'project', id: 'gua' })
    expect(parseStored('{"project":"gua","workspace":"survey"}')).toEqual({ kind: 'workspace', project: 'gua', id: 'survey' })
    expect(parseStored('{"project":"../etc"}')).toBeNull()
    expect(parseStored('{"project":"gua","workspace":"Bad Name"}')).toBeNull()
  })
  it('项目的世界与编辑台是两个世界', () => {
    expect(worldOf({ kind: 'home' })).toBe('projects')
    expect(worldOf({ kind: 'workspace', project: 'gua', id: 'survey' })).toBe('projects')
    expect(worldOf({ kind: 'studio' })).toBe('studio')
    expect(projectOf({ kind: 'workspace', project: 'gua', id: 'survey' })).toBe('gua')
    expect(projectOf({ kind: 'project', id: 'gua' })).toBe('gua')
    expect(projectOf({ kind: 'door' })).toBeNull()
  })
})
