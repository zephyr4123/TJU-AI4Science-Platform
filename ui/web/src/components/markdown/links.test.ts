import { describe, expect, it } from 'vitest'

import { relativeTo } from './links'

describe('relativeTo', () => {
  const overview = { ws: 'memory', path: 'writing/1/overview.md' }

  it('相对这份文件的路径按它所在的目录解开成项目内路径', () => {
    expect(relativeTo('../../literature/2/notes/3/note.md', overview)).toBe('workspaces/memory/literature/2/notes/3/note.md')
    expect(relativeTo('./figure.md', overview)).toBe('workspaces/memory/writing/1/figure.md')
    expect(relativeTo('notes/3/note.md', { ws: 'memory', path: 'literature/2/sources.md' })).toBe('workspaces/memory/literature/2/notes/3/note.md')
    expect(relativeTo('requirement.md', { ws: 'memory', path: 'README.md' })).toBe('workspaces/memory/requirement.md')
  })

  it('锚点去掉；只有锚点的不是文件', () => {
    expect(relativeTo('../2/sources.md#笔记', { ws: 'memory', path: 'literature/1/sources.md' })).toBe('workspaces/memory/literature/2/sources.md')
    expect(relativeTo('#笔记', overview)).toBeNull()
  })

  it('退出了工作区的不认', () => {
    expect(relativeTo('../../../other/x.md', overview)).toBeNull()
    expect(relativeTo('../..', overview)).toBeNull()
  })

  it('不是相对路径的原样交出去，由对话那套认（绝对路径、项目内路径、网址）', () => {
    expect(relativeTo('/Users/a/projects/p/workspaces/memory/x.md', overview)).toBeNull()
    expect(relativeTo('workspaces/memory/writing/1/overview.md', overview)).toBeNull()
    expect(relativeTo('file:///tmp/x.md', overview)).toBeNull()
    expect(relativeTo('https://arxiv.org/abs/2504.19413', overview)).toBeNull()
  })
})
