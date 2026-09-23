// favicon 与页面里内联的标是同一条路径：改了一处另一处不跟着改，浏览器标签页和页面上就是两个标。
/// <reference types="node" />
import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { LOGO_PATH } from './Logo'

const FAVICON = new URL('../../public/favicon.svg', import.meta.url).pathname

describe('平台的标', () => {
  it('favicon.svg 与 Logo 组件是同一条路径', () => {
    const svg = readFileSync(FAVICON, 'utf8')
    const d = / d="([^"]+)"/.exec(svg)?.[1]
    expect(d).toBe(LOGO_PATH)
    expect(svg).toContain('viewBox="0 0 64 64"')
    expect(svg).toContain('fill-rule="evenodd"')
  })
  it('路径是三段：瓶、星芒、液面（evenodd 才镂得空）', () => {
    expect(LOGO_PATH.split('M').length - 1).toBe(3)
    expect(LOGO_PATH.split('Z').length - 1).toBe(3)
  })
})
