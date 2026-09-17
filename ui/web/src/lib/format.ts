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

/** 对话列表里的名字：第一句话；还没说话就按开始时间叫它。 */
export function chatTitle(chat: { title: string | null; created_at: string }): string {
  return chat.title ?? `${when(chat.created_at)} 开始的对话`
}

/** 一段 Markdown 开头是不是一句短结论：第一段不超过 60 字、不是列表 / 标题 / 表格 / 代码，就把它单拎出来。 */
export function splitLede(markdown: string): { lede: string | null; rest: string } {
  const trimmed = markdown.trim()
  const cut = trimmed.search(/\n\s*\n/)
  const first = (cut === -1 ? trimmed : trimmed.slice(0, cut)).trim()
  const rest = cut === -1 ? '' : trimmed.slice(cut).trim()
  if (first.length === 0 || first.length > 60 || first.includes('\n') || /^([-*#>|`\d]|\d+\.)/.test(first)) {
    return { lede: null, rest: trimmed }
  }
  return { lede: first.replace(/\*\*/g, ''), rest }
}
