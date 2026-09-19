import { describe, expect, it } from 'vitest'

import { highlight, languageOf } from './highlight'

describe('代码高亮', () => {
  it('按后缀选语言，不认识的 null', () => {
    expect(languageOf('harness/evaluate.py')).toBe('python')
    expect(languageOf('scoring.yaml')).toBe('yaml')
    expect(languageOf('make_run0.sh')).toBe('bash')
    expect(languageOf('pyproject.toml')).toBe('ini')
    expect(languageOf('SHA256SUMS')).toBeNull()
    expect(languageOf('ledger.tsv')).toBeNull()
  })
  it('有语言就打标记，没语言只转义', () => {
    expect(highlight('def f():\n    return "x"', 'python')).toContain('hljs-keyword')
    expect(highlight('a < b', null)).toBe('a &lt; b')
    expect(highlight('<script>', 'python')).not.toContain('<script>')
  })
})
