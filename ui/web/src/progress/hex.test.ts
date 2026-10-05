import { describe, expect, it } from 'vitest'

import { center, ringsFor, spiral } from './hex'

const distance = ([q, r]: [number, number]) => (Math.abs(q) + Math.abs(r) + Math.abs(q + r)) / 2

describe('spiral', () => {
  it('第 0 格在正中，第 1–6 格是它的六个邻居，第 7–18 格是第二圈', () => {
    expect(spiral(0)).toEqual([0, 0])
    expect(Array.from({ length: 6 }, (_, i) => distance(spiral(i + 1)))).toEqual([1, 1, 1, 1, 1, 1])
    expect(Array.from({ length: 12 }, (_, i) => distance(spiral(i + 7)))).toEqual(Array(12).fill(2))
    expect(distance(spiral(19))).toBe(3)
  })

  it('前 127 格两两不重', () => {
    const seen = new Set(Array.from({ length: 127 }, (_, i) => spiral(i).join(',')))
    expect(seen.size).toBe(127)
  })

  it('一圈里相邻两格挨着（螺旋是连续的一条）', () => {
    for (let i = 1; i < 60; i += 1) {
      const [a, b] = [spiral(i), spiral(i + 1)]
      const near = distance([a[0] - b[0], a[1] - b[1]])
      expect(near === 1 || [6, 18, 36, 60].includes(i)).toBe(true)
    }
  })
})

describe('ringsFor', () => {
  it('放下 n 格要几圈', () => {
    expect([1, 2, 7, 8, 19, 20, 61, 62].map(ringsFor)).toEqual([0, 1, 1, 2, 2, 3, 4, 5])
  })
})

describe('center', () => {
  it('同一行相邻两格隔 √3 个半径，上下两行隔 1.5 个', () => {
    expect(center([1, 0], 10)[0]).toBeCloseTo(17.32, 2)
    expect(center([0, 1], 10)).toEqual([expect.closeTo(8.66, 2), 15])
  })
})
