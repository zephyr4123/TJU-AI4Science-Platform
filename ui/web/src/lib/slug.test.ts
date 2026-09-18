import { describe, expect, it } from 'vitest'

import { ID_RE, suggestId } from './slug'

const day = new Date(2026, 8, 18)

describe('suggestId', () => {
  it('拉丁词小写、连字符相连，中文忽略', () => {
    expect(suggestId('Rahman 模型多起点估计的稳定性', [], day)).toBe('rahman')
    expect(suggestId('MLP Regression on CIFAR', [], day)).toBe('mlp-regression-on-cifar')
  })
  it('没有拉丁字符就按日期', () => {
    expect(suggestId('一维函数回归的固定预算调参', [], day)).toBe('ws-0918')
    expect(suggestId('', [], day)).toBe('ws-0918')
  })
  it('数字开头补前缀，重音去掉', () => {
    expect(suggestId('3D 打印', [], day)).toBe('ws-3d')
    expect(suggestId('Schrödinger 方程', [], day)).toBe('schrodinger')
  })
  it('重名往后编号', () => {
    expect(suggestId('rahman', ['rahman'], day)).toBe('rahman-2')
    expect(suggestId('rahman', ['rahman', 'rahman-2'], day)).toBe('rahman-3')
  })
  it('太长截断且不以连字符收尾，结果总合法', () => {
    const id = suggestId('a'.repeat(30) + ' bbbbbbbbbbbbbbbbbbbbbb', [], day)
    expect(id.length).toBeLessThanOrEqual(40)
    expect(id.endsWith('-')).toBe(false)
    for (const t of ['Rahman 模型', '一维', '3D', 'Schrödinger', 'x y z']) expect(suggestId(t, [], day)).toMatch(ID_RE)
  })
})
