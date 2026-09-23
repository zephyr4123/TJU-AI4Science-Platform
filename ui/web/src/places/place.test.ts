import { describe, expect, it } from 'vitest'

import { projectOf, worldOf } from './place'

describe('地方', () => {
  it('项目的世界与编辑台是两个世界', () => {
    expect(worldOf({ kind: 'home' })).toBe('projects')
    expect(worldOf({ kind: 'workspace', project: 'gua', id: 'survey' })).toBe('projects')
    expect(worldOf({ kind: 'studio' })).toBe('studio')
    expect(projectOf({ kind: 'workspace', project: 'gua', id: 'survey' })).toBe('gua')
    expect(projectOf({ kind: 'project', id: 'gua' })).toBe('gua')
    expect(projectOf({ kind: 'door' })).toBeNull()
  })
})
