// 一个走着的表：从 `since` 起走了多久（6:12），`until` 给了就停在那一刻。进度面板与对话底部的「运行中」共用。
import { elapsed, useNow } from '@/lib/clock'
import { cn } from '@/lib/utils'

/** 从 `since` 起走了多久；`until` 给了就停在那一刻 */
export function Clock({ since, until, className }: { since: string; until?: string | null; className?: string }) {
  const now = useNow(!until)
  return <span className={cn('tabular-nums', className)}>{elapsed(since, until ?? now)}</span>
}
