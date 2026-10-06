// favicon 与页面里内联的标是同三条路径、同几种颜色：改了一处另一处不跟着改，浏览器标签页和页面上就是两个标。
/// <reference types="node" />
import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { MARK } from './Logo'

const read = (path: string) => readFileSync(new URL(path, import.meta.url).pathname, 'utf8')
const FAVICON = read('../../public/favicon.svg')
const CSS = read('../index.css')

describe('平台的标', () => {
  it('favicon.svg 与 Logo 组件是同三条路径、同一个画布', () => {
    expect([...FAVICON.matchAll(/ d="([^"]+)"/g)].map((m) => m[1])).toEqual([...MARK])
    expect(FAVICON).toContain('viewBox="0 0 64 64"')
  })
  it('favicon.svg 的浅色、深色与 index.css 的 --mark-1/2/3 一致', () => {
    // index.css 里三处：浅色、跟系统的深色、强制的深色；后两处得一样
    const tokens = [...CSS.matchAll(/--mark-\d: (#[0-9A-F]{6});/g)].map((m) => m[1])
    expect(tokens).toHaveLength(9)
    expect(tokens.slice(3, 6)).toEqual(tokens.slice(6, 9))
    const favicon = [...FAVICON.matchAll(/fill:(#[0-9A-F]{6})/g)].map((m) => m[1])
    expect(favicon).toEqual(tokens.slice(0, 6))
  })
})
