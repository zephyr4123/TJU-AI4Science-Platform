// 六边形螺旋（文献检索的收录蜂巢、精读的那堆文献共用这一种格子）：第 0 格在正中，之后一圈一圈往外，第 k 圈 6k 格。
// 轴坐标（q, r）、尖顶朝上；几何照 Red Blob Games 的 hexagon grids 一文。纯函数，有单测。

/** 轴坐标的六个方向，顺时针；第 k 圈从「左下」方向走出 k 步的那格起，再沿六个方向各走 k 步 */
const DIRECTIONS: readonly [number, number][] = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]]

/** 第 i 格的轴坐标 */
export function spiral(i: number): [number, number] {
  if (i === 0) return [0, 0]
  let k = 1
  while (1 + 3 * k * (k + 1) <= i) k += 1
  const j = i - (1 + 3 * k * (k - 1))
  const side = Math.floor(j / k)
  const step = j % k
  let q = DIRECTIONS[4][0] * k
  let r = DIRECTIONS[4][1] * k
  for (let s = 0; s < side; s += 1) {
    q += DIRECTIONS[s][0] * k
    r += DIRECTIONS[s][1] * k
  }
  return [q + DIRECTIONS[side][0] * step, r + DIRECTIONS[side][1] * step]
}

/** 放下 n 格要几圈（不算正中那格）：0 圈放 1 格，k 圈放 1 + 3k(k+1) 格 */
export function ringsFor(n: number): number {
  let k = 0
  while (1 + 3 * k * (k + 1) < n) k += 1
  return k
}

/** 轴坐标 → 格心的像素坐标（外接圆半径 size） */
export function center([q, r]: [number, number], size: number): [number, number] {
  return [size * Math.sqrt(3) * (q + r / 2), size * 1.5 * r]
}

/** 尖顶六边形六个顶点，给 SVG polygon 的 points */
export function hexPoints(cx: number, cy: number, size: number): string {
  return Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 180) * (60 * i - 30)
    return `${(cx + size * Math.cos(a)).toFixed(2)},${(cy + size * Math.sin(a)).toFixed(2)}`
  }).join(' ')
}

/** 尖顶六边形的 CSS clip-path（HTML 元素当格子用：精读那几堆） */
export const HEX_CLIP = 'polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%)'
