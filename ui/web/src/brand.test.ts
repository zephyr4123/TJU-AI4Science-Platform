// 名字只在 brand.ts 写一次；浏览器标签页的标题在 index.html 里，import 不到，这里对账。
/// <reference types="node" />
import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { BRAND } from './brand'

const INDEX = new URL('../index.html', import.meta.url).pathname

describe('平台的名字', () => {
  it('index.html 的标题就是名字', () => {
    expect(/<title>([^<]*)<\/title>/.exec(readFileSync(INDEX, 'utf8'))?.[1]).toBe(BRAND.name)
  })
  it('字标的两截拼起来就是名字', () => {
    expect(BRAND.parts.join('')).toBe(BRAND.name)
  })
})
