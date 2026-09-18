import { describe, expect, it } from 'vitest'

import { ASSETS, CDN_ORIGIN, COVERS, coverOf } from './assets'

function urls(node: unknown): string[] {
  if (typeof node === 'string') return node.split(/[\s,]+/).filter((s) => s.startsWith('http'))
  if (node && typeof node === 'object') return Object.values(node).flatMap(urls)
  return []
}

describe('素材清单', () => {
  const all = [...urls(ASSETS), ...urls(COVERS)]

  it('每条 URL 都在自己的 CDN 上、都走 https', () => {
    expect(all.length).toBeGreaterThan(0)
    for (const u of all) expect(new URL(u).origin).toBe(CDN_ORIGIN)
    expect(CDN_ORIGIN.startsWith('https://')).toBe(true)
  })

  it('视频是 mp4、首帧与配图是 jpg', () => {
    for (const theme of ['light', 'dark'] as const) {
      expect(ASSETS.door[theme].video.endsWith('.mp4')).toBe(true)
      expect(ASSETS.door[theme].poster.endsWith('.jpg')).toBe(true)
    }
    expect(ASSETS.welcome.src.endsWith('.jpg')).toBe(true)
  })

  it('封面按名字稳定地挑，六张都挑得到', () => {
    expect(coverOf('mlp-regression')).toBe(coverOf('mlp-regression'))
    const picked = new Set(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n'].map((id) => coverOf(id).key))
    expect(picked.size).toBe(COVERS.length)
  })
})
