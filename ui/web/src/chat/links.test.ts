import { describe, expect, it } from 'vitest'

import { localFile } from './links'

describe('对话里指向本项目文件的链接', () => {
  it('Codex 写的本机绝对路径：认出是哪个工作区里的哪个文件（外层 #231）', () => {
    const href = '/Users/x/ai4sci/projects/project-1005/workspaces/long-term-memory-review/writing/1/overview.md'
    expect(localFile(href, 'project-1005')).toEqual({ ws: 'long-term-memory-review', path: 'writing/1/overview.md' })
    expect(localFile(`file://${href}`, 'project-1005')).toEqual({ ws: 'long-term-memory-review', path: 'writing/1/overview.md' })
  })
  it('项目里的相对路径（指南教的写法），带不带 ./ 都认；行号尾巴去掉', () => {
    expect(localFile('workspaces/w1/literature/1/sources.md', 'p')).toEqual({ ws: 'w1', path: 'literature/1/sources.md' })
    expect(localFile('./workspaces/w1/literature/1/sources.md#L12', 'p')).toEqual({ ws: 'w1', path: 'literature/1/sources.md' })
    expect(localFile('workspaces/w1/literature/1/', 'p')).toEqual({ ws: 'w1', path: 'literature/1' })
  })
  it('别的项目、网址、只到工作区那一层的不认', () => {
    expect(localFile('/Users/x/projects/other/workspaces/w1/a.md', 'p')).toBeNull()
    expect(localFile('https://arxiv.org/abs/2410.10813', 'p')).toBeNull()
    expect(localFile('workspaces/w1', 'p')).toBeNull()
  })
})
