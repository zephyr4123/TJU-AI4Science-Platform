// 每种数据上次拿到的那一份，按名字记着（模块级，随页面活着，不落盘）：回到一个地方先摆上次的那份、
// 再在后台重拉，页面不闪骨架屏。名字是数据的身份（`project:gua`、`workspace:gua/survey`），不含「重拉的理由」（epoch）。

const seen = new Map<string, unknown>()

/** 上次拿到的那份；没名字或没见过就是 null */
export function recall<T>(key: string | undefined): T | null {
  if (key === undefined || !seen.has(key)) return null
  return seen.get(key) as T
}

export function keep(key: string | undefined, value: unknown): void {
  if (key !== undefined) seen.set(key, value)
}

/** 只给测试用：清空 */
export function forgetAll(): void {
  seen.clear()
}
