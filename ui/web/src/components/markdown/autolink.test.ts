import type { Root } from 'mdast'
import { describe, expect, it } from 'vitest'

import { remarkTrimAutolink, splitTrailingPunct } from './autolink'

describe('splitTrailingPunct', () => {
  it('结尾的中文标点切下来，ASCII 与正文里的不动', () => {
    expect(splitTrailingPunct('https://arxiv.org/abs/2609.01558）。')).toEqual({ url: 'https://arxiv.org/abs/2609.01558', tail: '）。' })
    expect(splitTrailingPunct('https://github.com/JingXiao10/GUA（MIT')).toEqual({ url: 'https://github.com/JingXiao10/GUA（MIT', tail: '' })
    expect(splitTrailingPunct('https://a.b/c?x=1')).toEqual({ url: 'https://a.b/c?x=1', tail: '' })
  })
})

describe('remarkTrimAutolink', () => {
  const autolink = (url: string) => ({ type: 'link', url, children: [{ type: 'text', value: url }] })

  it('自动链接结尾的标点挪成链接后面的文本；手写的 [文字](网址) 不动', () => {
    const tree = {
      type: 'root',
      children: [{ type: 'paragraph', children: [
        { type: 'text', value: '见 ' }, autolink('https://arxiv.org/abs/2609.01558）。'),
        { type: 'link', url: 'https://x.y）', children: [{ type: 'text', value: '论文' }] },
      ] }],
    } as unknown as Root
    remarkTrimAutolink()(tree)
    const para = tree.children[0] as { children: Array<{ type: string; url?: string; value?: string }> }
    expect(para.children.map((c) => [c.type, c.url ?? c.value])).toEqual([
      ['text', '见 '], ['link', 'https://arxiv.org/abs/2609.01558'], ['text', '）。'], ['link', 'https://x.y）'],
    ])
  })
})
