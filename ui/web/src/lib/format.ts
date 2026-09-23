// 数字与时间的显示口径，全页面只此一处：指标六位有效数字（与 CLI 的 `:.6g` 一致）、钱两位小数。

export function metric(value: number | null | undefined, digits = 6): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return String(Number(value.toPrecision(digits)))
}

/** 正文与大数字里的数：四位有效数字够读，精确值在细节层。 */
export const prose = (value: number | null | undefined) => metric(value, 4)

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

/** 只到天：「9 月 21 日」；跨年才带年。项目墙上「创建于」用它。 */
export function day(iso: string | null | undefined, today = new Date()): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const sameYear = date.getFullYear() === today.getFullYear()
  return date.toLocaleDateString('zh-CN', { year: sameYear ? undefined : 'numeric', month: 'long', day: 'numeric' })
}

/** 对话列表里的名字：第一句话；还没说话就按开始时间叫它。 */
export function chatTitle(chat: { title: string | null; created_at: string }): string {
  return chat.title ?? `${when(chat.created_at)} 开始的对话`
}

/** 文件大小：B / KB / MB，一位小数。 */
export function bytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}
