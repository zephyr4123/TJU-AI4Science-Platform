// 数字与时间的显示口径，全页面只此一处：指标六位有效数字（与 CLI 的 `:.6g` 一致）、钱两位小数。

export function metric(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const text = Number(value.toPrecision(6))
  return String(text)
}

export function usd(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `$${value.toFixed(2)}`
}

export function seconds(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)} s`
  const minutes = Math.floor(value / 60)
  return `${minutes} min ${Math.round(value - minutes * 60)} s`
}

export function when(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString('zh-CN', { hour12: false, month: 'numeric', day: 'numeric',
                                        hour: '2-digit', minute: '2-digit' })
}

export function shortHash(value: string | null | undefined): string {
  return value ? value.slice(0, 8) : '—'
}

/** 改进量：按方向取正，正数就是变好了。 */
export function improvement(
  baseline: number | null, best: number, direction: 'minimize' | 'maximize',
): number | null {
  if (baseline === null) return null
  return direction === 'minimize' ? baseline - best : best - baseline
}
