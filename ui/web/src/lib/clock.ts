// 已运行多久、每秒走一下：进度面板（progress/）与对话底部的「运行中」（外层 #242 #243）共用。
import { useEffect, useState } from 'react'

/** 每 `ms` 毫秒的此刻；`live` 为假时不走 */
export function useNow(live: boolean, ms = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!live) return
    const timer = setInterval(() => setNow(Date.now()), ms)
    return () => clearInterval(timer)
  }, [live, ms])
  return now
}

/** 两个时刻之间多久：一小时以内写 6:12，过了写 1:02:05；倒着的算 0 */
export function elapsed(since: string, until: number | string): string {
  const end = typeof until === 'number' ? until : Date.parse(until)
  const total = Math.max(0, Math.floor((end - Date.parse(since)) / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = String(total % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`
}
