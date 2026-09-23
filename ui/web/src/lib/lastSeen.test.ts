import { beforeEach, describe, expect, it } from 'vitest'

import { forgetAll, keep, recall } from './lastSeen'

describe('lastSeen', () => {
  beforeEach(forgetAll)

  it('按名字记上次那份；没名字不记、没见过是 null', () => {
    expect(recall('project:gua')).toBeNull()
    keep('project:gua', { id: 'gua' })
    expect(recall<{ id: string }>('project:gua')).toEqual({ id: 'gua' })
    keep(undefined, { id: 'x' })
    expect(recall(undefined)).toBeNull()
  })

  it('同名覆盖，null 也算一份（对话还没开就是 null）', () => {
    keep('chat:a', { turns: 1 })
    keep('chat:a', null)
    expect(recall('chat:a')).toBeNull()
    keep('chat:a', { turns: 2 })
    expect(recall<{ turns: number }>('chat:a')?.turns).toBe(2)
  })
})
