import { describe, expect, it } from 'vitest'

import { composing, isWebKit } from './browser'

describe('哪些是 WebKit（玻璃组件据此不走 SVG 折射，外层 #282）', () => {
  it('Safari 与桌面 App 的 WKWebView 都是：WKWebView 的 UA 没有 Safari 这个词（macOS 26.5.2 实测）', () => {
    expect(isWebKit('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko)')).toBe(true)
    expect(isWebKit('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15')).toBe(true)
    expect(isWebKit('Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1')).toBe(true)
    // iOS 上的 Chrome、Edge 也是 WebKit 内核，UA 里写的是 CriOS、EdgiOS
    expect(isWebKit('Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/140.0.7339.122 Mobile/15E148 Safari/604.1')).toBe(true)
    expect(isWebKit('Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 EdgiOS/140.3485.94 Mobile/15E148 Safari/605.1.15')).toBe(true)
  })
  it('Chromium 一族不是：Chrome、Edge、Windows 桌面 App 的 WebView2（UA 里也写着 AppleWebKit 与 Safari）', () => {
    expect(isWebKit('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36')).toBe(false)
    expect(isWebKit('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36 Edg/154.0.0.0')).toBe(false)
    expect(isWebKit('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chromium/140.0.0.0 Safari/537.36')).toBe(false)
  })
  it('Firefox 与认不出的不是', () => {
    expect(isWebKit('Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:142.0) Gecko/20100101 Firefox/142.0')).toBe(false)
    expect(isWebKit('')).toBe(false)
  })
})

describe('输入法组词时的按键（回车是选词，不是发送，外层 #282）', () => {
  it('Chromium 与 Firefox：组词时 isComposing 是真', () => {
    expect(composing({ isComposing: true, keyCode: 229 })).toBe(true)
    expect(composing({ isComposing: true, keyCode: 13 })).toBe(true)
  })
  it('WebKit 用回车确认候选词的那次：isComposing 是假、keyCode 是 229（WebKit bug 165004）', () => {
    expect(composing({ isComposing: false, keyCode: 229 })).toBe(true)
  })
  it('没在组词的回车与 Esc 不算', () => {
    expect(composing({ isComposing: false, keyCode: 13 })).toBe(false)
    expect(composing({ isComposing: false, keyCode: 27 })).toBe(false)
  })
})
